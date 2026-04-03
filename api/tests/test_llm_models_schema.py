from schemas.llm_providers import LLM_Models, LLM_ModelsListResponse


def test_llm_models_accepts_generic_payload():
    model = LLM_Models(
        id="claude-opus-4-6",
        capabilities={
            "batch": {"supported": True},
            "thinking": {
                "supported": True,
                "types": {
                    "adaptive": {"supported": True},
                },
            },
        },
        created_at="2026-02-04T00:00:00Z",
        display_name="Claude Opus 4.6",
        max_input_tokens=0,
        max_tokens=0,
        type="model",
    )

    assert model.id == "claude-opus-4-6"
    assert model.display_name == "Claude Opus 4.6"
    assert model.type == "model"
    assert model.capabilities["batch"]["supported"] is True
    assert model.capabilities["thinking"]["types"]["adaptive"]["supported"] is True


def test_llm_models_list_response_wraps_model_collection():
    response = LLM_ModelsListResponse(
        models=[
            LLM_Models(
                id="claude-opus-4-6",
                capabilities={"batch": {"supported": True}},
                created_at="2026-02-04T00:00:00Z",
                display_name="Claude Opus 4.6",
                max_input_tokens=0,
                max_tokens=0,
                type="model",
            ),
            LLM_Models(
                id="gpt-4.1",
                capabilities={"structured_outputs": {"supported": True}},
                created_at="2026-01-01T00:00:00Z",
                display_name="GPT-4.1",
                max_input_tokens=0,
                max_tokens=0,
                type="model",
            ),
        ]
    )

    assert len(response.models) == 2
    assert response.models[0].id == "claude-opus-4-6"
    assert response.models[1].id == "gpt-4.1"
