"""Shared PyTorch sequence model implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset, TensorDataset
except ImportError:  # pragma: no cover - optional dependency.
    torch = None
    nn = None
    DataLoader = None
    Dataset = None
    TensorDataset = None

from capm.domains.prediction import (
    DatasetAdaptationError,
    MissingOptionalDependencyError,
    SequencePredictionInput,
    SequenceTrainingInput,
)


def require_torch() -> None:
    """Raise a helpful error when PyTorch is not installed."""
    if torch is None or nn is None or DataLoader is None or Dataset is None or TensorDataset is None:
        raise MissingOptionalDependencyError(
            "Deep-learning models require the optional `deep-learning` dependencies (`torch`)."
        )


def resolve_torch_device(requested_device: str) -> Any:
    """Resolve an explicit or automatic PyTorch device."""
    require_torch()
    normalized = requested_device.strip().lower()
    if normalized in {"", "auto"}:
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if normalized == "cuda" and not torch.cuda.is_available():
        raise MissingOptionalDependencyError("Requested CUDA device, but CUDA is not available.")
    if normalized == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
        raise MissingOptionalDependencyError("Requested MPS device, but Apple Metal/MPS is not available.")
    return torch.device(normalized)


class _RecurrentRegressor(nn.Module if nn is not None else object):
    """Small sequence-to-one recurrent regressor."""

    def __init__(
        self,
        *,
        cell_type: str,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        recurrent_dropout = dropout if num_layers > 1 else 0.0
        recurrent_cls = nn.LSTM if cell_type == "lstm" else nn.GRU
        self.recurrent = recurrent_cls(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=recurrent_dropout,
        )
        self.output = nn.Linear(hidden_size, 1)

    def forward(self, values):  # type: ignore[no-untyped-def]
        """Return one scalar forecast per sequence."""
        recurrent_output, _hidden = self.recurrent(values)
        return self.output(recurrent_output[:, -1, :]).squeeze(-1)


class _WindowedSequenceDataset(Dataset if Dataset is not None else object):
    """Torch dataset that slices overlapping windows lazily from one feature matrix."""

    def __init__(self, feature_matrix: Any, target_values: Any, reference_indices: Any, sequence_length: int) -> None:
        self.features = torch.as_tensor(feature_matrix, dtype=torch.float32)
        self.targets = torch.as_tensor(target_values, dtype=torch.float32)
        self.reference_indices = torch.as_tensor(reference_indices, dtype=torch.long)
        self.sequence_length = int(sequence_length)

    def __len__(self) -> int:
        return int(len(self.reference_indices))

    def __getitem__(self, index: int):  # type: ignore[no-untyped-def]
        reference_index = int(self.reference_indices[index])
        start = reference_index - self.sequence_length + 1
        return self.features[start : reference_index + 1], self.targets[index]


@dataclass(slots=True)
class RecurrentForecastingModel:
    """Fits and predicts with a PyTorch recurrent regressor."""

    cell_type: str
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    _model: Any | None = field(init=False, default=None, repr=False)
    _feature_names: tuple[str, ...] = field(init=False, default=(), repr=False)

    family: str = "deep_learning"

    @property
    def name(self) -> str:
        """Return the registry model name."""
        return self.cell_type

    def _parameters(self) -> dict[str, Any]:
        parameters = {
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.1,
            "learning_rate": 0.001,
            "batch_size": 512,
            "max_epochs": 20,
            "early_stopping_patience": 3,
            "weight_decay": 0.0,
            "seed": 42,
            "device": "auto",
            "progress_callback": None,
        }
        parameters.update(self.model_kwargs)
        return parameters

    def fit(self, training_input: SequenceTrainingInput) -> dict[str, Any]:
        """Fit the recurrent model."""
        require_torch()
        if not isinstance(training_input, SequenceTrainingInput):
            raise DatasetAdaptationError(f"{self.name.upper()} expects a sequence training input.")
        parameters = self._parameters()
        progress_callback = parameters.pop("progress_callback", None)
        torch.manual_seed(int(parameters["seed"]))
        device = resolve_torch_device(str(parameters["device"]))
        if progress_callback is not None:
            progress_callback(f"using torch device: {device}")
        sequences = torch.tensor(training_input.sequences, dtype=torch.float32, device=device)
        targets = torch.tensor(training_input.target_values, dtype=torch.float32, device=device)
        dataset = TensorDataset(sequences, targets)
        loader = DataLoader(dataset, batch_size=int(parameters["batch_size"]), shuffle=True)
        losses = self._fit_loader(
            loader=loader,
            input_size=len(training_input.feature_names),
            parameters=parameters,
            device=device,
            progress_callback=progress_callback,
        )
        self._feature_names = tuple(training_input.feature_names)
        return {
            "framework": "torch",
            "training_rows": len(training_input.target_values),
            "feature_names": list(training_input.feature_names),
            "loss_curve": losses,
            "model_kwargs": parameters,
        }

    def fit_array_dataset(self, training_dataset: Any) -> dict[str, Any]:
        """Fit from a compact array-backed sequence dataset."""
        require_torch()
        parameters = self._parameters()
        progress_callback = parameters.pop("progress_callback", None)
        torch.manual_seed(int(parameters["seed"]))
        device = resolve_torch_device(str(parameters["device"]))
        if progress_callback is not None:
            progress_callback(f"using torch device: {device}")
        dataset = _WindowedSequenceDataset(
            training_dataset.feature_matrix,
            training_dataset.target_values,
            training_dataset.reference_indices,
            training_dataset.sequence_length,
        )
        loader = DataLoader(dataset, batch_size=int(parameters["batch_size"]), shuffle=True)
        losses = self._fit_loader(
            loader=loader,
            input_size=len(training_dataset.feature_names),
            parameters=parameters,
            device=device,
            progress_callback=progress_callback,
        )
        self._feature_names = tuple(training_dataset.feature_names)
        return {
            "framework": "torch",
            "training_rows": len(training_dataset.target_values),
            "feature_names": list(training_dataset.feature_names),
            "loss_curve": losses,
            "model_kwargs": parameters,
        }

    def predict_array_dataset(self, prediction_dataset: Any, *, batch_size: int) -> tuple[float, ...]:
        """Predict all samples from a compact array-backed sequence dataset in batches."""
        require_torch()
        if self._model is None:
            raise DatasetAdaptationError(f"The {self.name.upper()} model must be fit before prediction.")
        dataset = _WindowedSequenceDataset(
            prediction_dataset.feature_matrix,
            prediction_dataset.target_values,
            prediction_dataset.reference_indices,
            prediction_dataset.sequence_length,
        )
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
        device = next(self._model.parameters()).device
        predictions: list[float] = []
        self._model.eval()
        with torch.no_grad():
            for batch_x, _batch_y in loader:
                batch_prediction = self._model(batch_x.to(device)).detach().cpu()
                predictions.extend(float(value) for value in batch_prediction)
        return tuple(predictions)

    def _fit_loader(
        self,
        *,
        loader: Any,
        input_size: int,
        parameters: dict[str, Any],
        device: Any,
        progress_callback: Any,
    ) -> list[float]:
        self._model = _RecurrentRegressor(
            cell_type=self.cell_type,
            input_size=input_size,
            hidden_size=int(parameters["hidden_size"]),
            num_layers=int(parameters["num_layers"]),
            dropout=float(parameters["dropout"]),
        ).to(device)
        optimizer = torch.optim.Adam(
            self._model.parameters(),
            lr=float(parameters["learning_rate"]),
            weight_decay=float(parameters["weight_decay"]),
        )
        loss_fn = nn.MSELoss()
        losses: list[float] = []
        max_epochs = int(parameters["max_epochs"])
        for epoch in range(max_epochs):
            self._model.train()
            total_loss = 0.0
            total_count = 0
            for batch_x, batch_y in loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)
                optimizer.zero_grad()
                prediction = self._model(batch_x)
                loss = loss_fn(prediction, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += float(loss.detach().cpu()) * len(batch_x)
                total_count += len(batch_x)
            epoch_loss = total_loss / max(total_count, 1)
            losses.append(epoch_loss)
            if progress_callback is not None:
                progress_callback(f"epoch {epoch + 1}/{max_epochs} loss={epoch_loss:.8f}")
        return losses

    def predict(self, prediction_input: SequencePredictionInput) -> tuple[float, dict[str, Any]]:
        """Predict one scalar target from one sequence."""
        require_torch()
        if self._model is None:
            raise DatasetAdaptationError(f"The {self.name.upper()} model must be fit before prediction.")
        if not isinstance(prediction_input, SequencePredictionInput):
            raise DatasetAdaptationError(f"{self.name.upper()} expects a sequence prediction input.")
        device = next(self._model.parameters()).device
        sequence = torch.tensor([prediction_input.sequence], dtype=torch.float32, device=device)
        self._model.eval()
        with torch.no_grad():
            predicted_value = float(self._model(sequence).detach().cpu()[0])
        return predicted_value, {
            "prediction_time": prediction_input.prediction_time.isoformat(),
            "feature_names": list(prediction_input.feature_names),
            "sequence_length": len(prediction_input.sequence),
        }
