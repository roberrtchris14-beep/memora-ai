import time
import logging
import threading
from typing import List, Optional
from app.learning.skill_generator import SkillGenerator
from app.learning.skill_registry_enhancer import SkillRegistryEnhancer

logger = logging.getLogger(__name__)


class AutoIntegrator:
    def __init__(
        self,
        skill_generator: SkillGenerator,
        skill_enhancer: SkillRegistryEnhancer,
        threshold: float = 0.8,
    ):
        self.skill_generator = skill_generator
        self.skill_enhancer = skill_enhancer
        self.threshold = threshold
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def check_and_integrate(self) -> List[str]:
        """
        Scan proposals for status='proposed' and confidence_score >= threshold,
        integrate each into the registry, and log the event.
        """
        integrated: List[str] = []
        try:
            proposals = self.skill_generator.get_proposals(status="proposed")
            for prop in proposals:
                if prop.confidence_score >= self.threshold:
                    logger.info(
                        f"[AutoIntegrator] Triggering integration for '{prop.skill_name}' "
                        f"(Confidence: {prop.confidence_score:.2f} >= {self.threshold:.2f})"
                    )
                    success = self.skill_enhancer.integrate_proposal(prop)
                    if success:
                        logger.info(
                            f"[AutoIntegrator] Successfully integrated and activated skill: '{prop.skill_name}'"
                        )
                        integrated.append(prop.skill_name)
                    else:
                        logger.warning(
                            f"[AutoIntegrator] Failed to integrate proposal: '{prop.skill_name}'"
                        )
        except Exception as e:
            logger.error(f"[AutoIntegrator] Error during check_and_integrate: {e}", exc_info=True)

        return integrated

    def _loop_worker(self, interval_seconds: int) -> None:
        logger.info(f"[AutoIntegrator] Background auto-integration loop started (interval={interval_seconds}s).")
        while self._running:
            try:
                self.check_and_integrate()
            except Exception as e:
                logger.error(f"[AutoIntegrator] Uncaught exception in loop worker: {e}", exc_info=True)

            # Sleep in 1-second chunks for responsive thread stopping
            for _ in range(max(1, interval_seconds)):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("[AutoIntegrator] Background auto-integration loop stopped.")

    def auto_integrate_loop(self, interval_seconds: int = 60) -> threading.Thread:
        """
        Start the auto-integration worker loop in a background daemon thread.
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.info("[AutoIntegrator] Background loop is already running.")
                return self._thread

            self._running = True
            self._thread = threading.Thread(
                target=self._loop_worker,
                args=(interval_seconds,),
                daemon=True,
                name="AutoIntegratorThread",
            )
            self._thread.start()
            return self._thread

    def stop(self) -> None:
        """Stop the background auto-integration loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
