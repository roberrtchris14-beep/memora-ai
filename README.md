# Deploying Memora to Render.com

Follow these step-by-step instructions to deploy your Memora application to Render for free.

## Step 1: Prepare your Repository
Make sure all your project files are pushed to a public or private repository on GitHub or GitLab.
The repository must contain:
- `main.py` (FastAPI entrypoint)
- `requirements.txt`
- `Dockerfile`
- `.dockerignore`
- `render.yaml`

## Step 2: Create a Web Service on Render
1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** in the top-right corner and select **Web Service**.
3. Connect your GitHub or GitLab account and select the **Memora** repository.

## Step 3: Configure Service Details
- **Name:** `memora` (or any unique name)
- **Region:** Choose the region closest to you
- **Branch:** `main` (or your active branch)
- **Runtime:** `Docker` (Render automatically detects the Dockerfile)
- **Instance Type:** `Free`

## Step 4: Add Environment Variables
Under the **Environment** tab, click **Add Environment Variable** and add:
- **Key:** `GEMINI_API_KEY`
- **Value:** *Your actual Gemini API Key from Google AI Studio*

## Step 5: Deploy
Click **Deploy Web Service** at the bottom of the page. Render will build the Docker container and deploy the applet on a secure `onrender.com` URL.
