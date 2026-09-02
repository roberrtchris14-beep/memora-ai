from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import json
import google.generativeai as genai
from app.core.config import GEMINI_API_KEY

# Ensure gemini API is configured
genai.configure(api_key=GEMINI_API_KEY)

class AgentState(TypedDict):
    messages: list
    session_id: str
    next_step: str

def clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]
    return text

class Orchestrator:
    def __init__(self, registry, vector_store):
        self.registry = registry
        self.vector_store = vector_store

        # Initialize StateGraph
        builder = StateGraph(AgentState)

        # Register nodes
        builder.add_node("agent", self.call_agent)
        builder.add_node("tools", self.call_tool)

        # Set Entry Point
        builder.set_entry_point("agent")

        # Set Conditional Edges & Standard Edge
        builder.add_conditional_edges(
            "agent",
            self.router,
            {"tools": "tools", "end": END}
        )
        builder.add_edge("tools", "agent")

        self.graph = builder.compile()

    def call_agent(self, state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        
        # Build tools description
        tools_info = ""
        for name, skill in self.registry.skills.items():
            tools_info += f"- name: {name}\n  description: {skill.description}\n"

        # Construct dialogue/history for the agent
        chat_history = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if "result" in msg:
                chat_history += f"Tool Output: {msg['result']}\n"
            elif "action" in msg:
                chat_history += f"Agent Intent: Action={msg['action']}, Input={msg.get('input')}\n"
            else:
                chat_history += f"{role.capitalize()}: {content}\n"

        system_instruction = (
            "You are Memora, an intelligent AI agent with persistent memory and custom skills.\n"
            "Decide if you need to use a tool (calculator, time, web_search, save_note) or just reply directly.\n\n"
            "Available tools:\n"
            f"{tools_info}\n"
            "You MUST output ONLY a valid JSON object matching one of the following formats, with NO extra conversational text outside of it:\n"
            "For tool use:\n"
            '{"action": "tool_name", "input": {"param_name": "param_value"}}\n'
            "For a direct reply:\n"
            '{"action": "reply", "response": "Your response to the user here"}\n'
        )

        full_prompt = (
            f"{system_instruction}\n"
            f"Conversation History:\n{chat_history}\n"
            "Your Next Action (JSON):"
        )

        models_to_try = ["models/gemini-2.5-flash", "models/gemini-3.5-flash", "models/gemini-pro-latest"]
        raw_response = ""
        last_err = None

        for m_name in models_to_try:
            try:
                model = genai.GenerativeModel(m_name)
                res = model.generate_content(full_prompt)
                if res and hasattr(res, "text") and res.text:
                    raw_response = res.text.strip()
                    break
            except Exception as e:
                last_err = e
                continue

        if not raw_response:
            # Fallback direct reply if generation fails
            fallback_response = {"action": "reply", "response": f"I encountered an error planning the next step: {last_err}"}
            messages.append({"role": "assistant", "content": fallback_response["response"]})
            state["messages"] = messages
            state["next_step"] = "end"
            return state

        # Parse output
        try:
            cleaned = clean_json_text(raw_response)
            parsed = json.loads(cleaned)
            action = parsed.get("action", "reply")
            
            if action == "reply":
                response_text = parsed.get("response", "")
                messages.append({"role": "assistant", "content": response_text})
                state["messages"] = messages
                state["next_step"] = "end"
            else:
                # Tool action
                tool_input = parsed.get("input", {})
                messages.append({
                    "role": "assistant",
                    "action": action,
                    "input": tool_input,
                    "content": f"Decided to run tool: {action}"
                })
                state["messages"] = messages
                state["next_step"] = "tools"
        except Exception as e:
            # Parse failed, treat raw output as response
            messages.append({"role": "assistant", "content": raw_response})
            state["messages"] = messages
            state["next_step"] = "end"

        return state

    def call_tool(self, state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        if not messages:
            state["next_step"] = "agent"
            return state

        # Find last tool decision
        last_decision = None
        for msg in reversed(messages):
            if "action" in msg and msg.get("action") != "reply":
                last_decision = msg
                break

        if not last_decision:
            state["next_step"] = "agent"
            return state

        tool_name = last_decision["action"]
        tool_input = last_decision.get("input", {})

        # Fetch and execute tool
        skill = self.registry.get_skill(tool_name)
        if not skill:
            result = {"error": f"Tool '{tool_name}' is not registered in the Skill Library.", "status": "error"}
        else:
            try:
                # Ensure save_note gets vector_store references or passes it down
                result = skill.execute(**tool_input)
            except Exception as e:
                result = {"error": str(e), "status": "error"}

        # Append result to messages list
        messages.append({
            "role": "tool",
            "name": tool_name,
            "result": json.dumps(result),
            "content": f"Tool {tool_name} returned result: {result}"
        })
        state["messages"] = messages
        # Return state with instruction to cycle back to agent
        state["next_step"] = "agent"
        return state

    def router(self, state: AgentState) -> str:
        next_step = state.get("next_step", "end")
        if next_step == "tools":
            return "tools"
        return "end"

    def run(self, user_message: str, session_id: str = "default") -> str:
        # Construct initial state
        initial_state: AgentState = {
            "messages": [{"role": "user", "content": user_message}],
            "session_id": session_id,
            "next_step": "agent"
        }
        
        # Stream or run to completion
        final_state = self.graph.invoke(initial_state)
        
        # Get last assistant reply
        response_text = "No response generated."
        final_messages = final_state.get("messages", [])
        for msg in reversed(final_messages):
            if msg.get("role") == "assistant" and "content" in msg and "action" not in msg:
                response_text = msg["content"]
                break
        else:
            if final_messages:
                response_text = final_messages[-1].get("content", "Completed processing.")

        # Save context to ChromaDB
        try:
            self.vector_store.add_memory(
                text=f"User asked: {user_message}, Agent replied: {response_text}",
                metadata={"session_id": session_id, "type": "conversation"}
            )
        except Exception as e:
            print(f"Warning: Failed to save interaction to memory: {e}")

        return response_text
