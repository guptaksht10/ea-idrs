from src.service.schemas import ExperimentRunRequest, ExperimentSummaryResponse
from src.service.shift_simulator import run_controlled_experiment


@app.get("/baseline-metrics")
def get_baseline_metrics():
    """Returns Experiment A per-class precision, recall, and F1 report."""
    metrics_path = settings.ARTIFACTS_DIR / "baseline_metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="baseline_metrics.json not found.")
    with open(metrics_path, encoding="utf-8") as f:
        return json.load(f)


@app.post("/run-experiment", response_model=ExperimentSummaryResponse)
def run_experiment_endpoint(req: ExperimentRunRequest) -> ExperimentSummaryResponse:
    """Runs controlled shift replay (Experiments B/C/E/F) and returns M1-M4 comparison."""
    if store.engine is None or store.monitor is None or store.test_df is None:
        raise HTTPException(status_code=503, detail="Artifacts or test stream not loaded.")
    if req.target_attack not in store.engine.label_encoder.classes_:
        raise HTTPException(status_code=400, detail=f"Unknown target_attack: {req.target_attack}")

    result = run_controlled_experiment(
        test_df=store.test_df,
        feature_cols=store.feature_cols,
        engine=store.engine,
        monitor=store.monitor,
        target_attack=req.target_attack,
        shift_type=req.shift_type,
        shift_start_window=req.shift_start_window,
        max_windows=req.max_windows,
        recall_cutoff=req.recall_cutoff,
    )
    return ExperimentSummaryResponse(**result)