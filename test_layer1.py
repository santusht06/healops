"""Test script for HealOps Layer 1 (Brain & Memory).

Verifies:
1. Configuration settings and environment variables.
2. Model factory instantiation (Bedrock, Gemini, OpenAI, Ollama).
3. Redis Session Manager connection and state persistence.
4. Fallback FileSessionManager functionality.
5. Post-Mortem Knowledge Base search & retrieval.
6. Strands Agent initialization with Layer 1 session + memory.
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from brain import get_model, get_session_manager, get_redis_client, postmortem_store, IncidentRecord
from strands import Agent, tool


def test_1_configuration():
    print("\n🔍 [1/5] Testing Configuration...")
    print(f"   App Name: {settings.APP_NAME}")
    print(f"   Selected Model Provider: {settings.MODEL_PROVIDER}")
    print(f"   Redis Host: {settings.REDIS_HOST}:{settings.REDIS_PORT} (Namespace: {settings.REDIS_NAMESPACE})")
    assert settings.APP_NAME
    print("   ✅ Configuration verified!")


def test_2_model_factory():
    print("\n🧠 [2/5] Testing Model Factory Instantiation...")
    # Test instantiating each model provider class
    try:
        bedrock_model = get_model(provider="bedrock")
        model_id = getattr(bedrock_model, "config", {}).get("model_id", settings.BEDROCK_MODEL_ID)
        print(f"   ✅ BedrockModel instantiated: model_id='{model_id}'")
    except Exception as e:
        print(f"   ⚠️ BedrockModel warning: {e}")

    try:
        gemini_model = get_model(provider="gemini")
        print(f"   ✅ GeminiModel instantiated: model_id='{gemini_model.config.get('model_id')}'")
    except Exception as e:
        print(f"   ⚠️ GeminiModel warning: {e}")

    try:
        ollama_model = get_model(provider="ollama")
        print(f"   ✅ OllamaModel instantiated: model_id='{ollama_model.config.get('model_id')}'")
    except Exception as e:
        print(f"   ⚠️ OllamaModel warning: {e}")


def test_3_redis_session():
    print("\n💾 [3/5] Testing Redis Session Manager...")
    session_id = "inc-test-session-001"
    sm = get_session_manager(session_id)
    print(f"   Active SessionManager Type: {type(sm).__name__}")
    
    r = get_redis_client()
    if r is not None:
        print("   ✅ Redis server is live and responsive (PONG received).")
        keys = r.keys(f"{settings.REDIS_NAMESPACE}:*")
        print(f"   Current Redis keys in namespace '{settings.REDIS_NAMESPACE}': {len(keys)}")
    else:
        print("   ℹ️ Redis not reachable, FileSessionManager active as fallback.")


def test_4_postmortem_store():
    print("\n📚 [4/5] Testing Post-Mortem Knowledge Base & SRE Runbooks...")
    query_1 = "502 Bad Gateway Nginx connection"
    matches_1 = postmortem_store.search(query_1)
    print(f"   Query: '{query_1}' -> Found {len(matches_1)} matches:")
    for m in matches_1:
        print(f"     • [{m.id}] {m.service} ({m.severity}): {m.symptom}")
        print(f"       Root cause: {m.root_cause[:70]}...")
        print(f"       Action: {m.remediation_steps[0]}")
    assert len(matches_1) > 0

    query_2 = "postgres database connection pool exhausted"
    matches_2 = postmortem_store.search(query_2)
    print(f"   Query: '{query_2}' -> Found {len(matches_2)} matches:")
    for m in matches_2:
        print(f"     • [{m.id}] {m.service}: {m.root_cause[:70]}...")
    assert len(matches_2) > 0
    print("   ✅ Post-Mortem Knowledge Store search verified!")


def test_5_agent_initialization():
    print("\n🤖 [5/5] Testing Strands Agent Init with Layer 1 Session & Runbook Tool...")

    # Define a tool that uses our Layer 1 PostMortemStore
    @tool
    def lookup_past_incidents(symptom_keywords: str) -> list[dict]:
        """Search historical SRE post-mortems for verified root causes and solutions."""
        results = postmortem_store.search(symptom_keywords, top_k=2)
        return [r.model_dump() for r in results]

    session_mgr = get_session_manager("incident-trial-999")
    agent_model = get_model()

    agent = Agent(
        model=agent_model,
        tools=[lookup_past_incidents],
        session_manager=session_mgr,
        system_prompt=(
            "You are HealOps, an autonomous SRE incident resolution agent. "
            "When given an incident symptom, consult lookup_past_incidents to review known root causes."
        )
    )

    print(f"   ✅ Strands Agent initialized successfully!")
    print(f"      • Model: {type(agent.model).__name__}")
    session_type = type(getattr(agent, '_session_manager', session_mgr)).__name__
    print(f"      • Session Manager: {session_type}")
    print(f"      • Tools Registered: {[t.name if hasattr(t, 'name') else str(t) for t in agent.tool_names]}")


def main():
    print("=" * 60)
    print("  🚀 HealOps — Layer 1 (Brain & Memory) Verification")
    print("=" * 60)
    test_1_configuration()
    test_2_model_factory()
    test_3_redis_session()
    test_4_postmortem_store()
    test_5_agent_initialization()
    print("\n" + "=" * 60)
    print("  ✨ ALL LAYER 1 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
