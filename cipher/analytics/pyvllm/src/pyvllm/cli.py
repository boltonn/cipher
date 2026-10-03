"""`pyvllm up|down|status|logs <model>` -- manage the local vLLM models (`llm`, `ocr`)."""

from typing import Annotated

import typer

from pyvllm.models import MODELS
from pyvllm.server import is_healthy, log_path, running_pid, served_models, start, stop

app = typer.Typer(help="Local models on one vLLM install", no_args_is_help=True)

Names = Annotated[list[str] | None, typer.Argument(help=f"Models: {', '.join(MODELS)}. Default: all")]


def _specs(names: list[str] | None):
    unknown = set(names or []) - set(MODELS)
    if unknown:
        raise typer.BadParameter(f"unknown model(s) {sorted(unknown)} -- choose from {list(MODELS)}")
    return [MODELS[name] for name in names or MODELS]


@app.command()
def up(names: Names = None, gpu: Annotated[int | None, typer.Option(help="Override the GPU")] = None) -> None:
    """Start models and wait until they answer."""
    for spec in _specs(names):
        start(spec, gpu=gpu)


@app.command()
def down(names: Names = None) -> None:
    """Stop models this analytic started."""
    for spec in _specs(names):
        if not stop(spec):
            typer.echo(f"{spec.name}: not started by pyvllm")


@app.command()
def status() -> None:
    """Which models are serving, where."""
    for spec in MODELS.values():
        other = served_models(spec)
        if is_healthy(spec):
            state = "serving"
        elif other:
            state = f"port taken by {', '.join(other)}"
        else:
            state = "starting" if running_pid(spec) else "down"
        typer.echo(f"{spec.name:4} {spec.served_name:22} {spec.base_url}  GPU {spec.gpu}  {state}")


@app.command()
def logs(name: str, lines: int = 40) -> None:
    """Tail a model's server log."""
    path = log_path(MODELS[name])
    typer.echo("\n".join(path.read_text().splitlines()[-lines:]) if path.exists() else f"no log at {path}")
