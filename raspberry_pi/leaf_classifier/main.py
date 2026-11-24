"""Classify individual leaf photographs with the supplied ONNX model."""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps


BASE = Path(__file__).resolve().parent
RESIZE_SIZE = 256
CROP_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TEMPERATURE = 1.210394024848938


def _validate_model_contract(session, labels):
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError("FRI model must expose exactly one input and one output")

    input_shape = list(inputs[0].shape)
    output_shape = list(outputs[0].shape)
    expected_input = ["batch", 3, 224, 224]
    expected_output = ["batch", 15]
    if input_shape != expected_input:
        raise ValueError(
            f"FRI model input contract mismatch: {input_shape!r} != {expected_input!r}"
        )
    if output_shape != expected_output:
        raise ValueError(
            f"FRI model output contract mismatch: {output_shape!r} != {expected_output!r}"
        )
    if not isinstance(labels, list) or len(labels) != 15:
        raise ValueError("FRI labels.json must contain an ordered list of 15 labels")
    if not all(isinstance(label, str) and label for label in labels):
        raise ValueError("FRI labels.json contains an invalid label")


def load_model():
    """Load the exact bundled model and ordered labels once."""
    model_path = BASE / "model.onnx"
    labels_path = BASE / "labels.json"
    if not model_path.is_file():
        raise FileNotFoundError(f"FRI model is missing: {model_path}")
    if not labels_path.is_file():
        raise FileNotFoundError(f"FRI labels are missing: {labels_path}")

    session = ort.InferenceSession(
        str(model_path), providers=["CPUExecutionProvider"]
    )
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    _validate_model_contract(session, labels)
    return session, labels


def prepare_image(image_path):
    """Convert a photograph to the exact tensor expected by the FRI model."""
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        image = image.convert("RGB")
    width, height = image.size
    long_side = int(RESIZE_SIZE * max(width, height) / min(width, height))
    size = (RESIZE_SIZE, long_side) if width <= height else (long_side, RESIZE_SIZE)
    image = image.resize(size, Image.Resampling.BILINEAR)
    left = round((image.width - CROP_SIZE) / 2)
    top = round((image.height - CROP_SIZE) / 2)
    image = image.crop((left, top, left + CROP_SIZE, top + CROP_SIZE))
    pixels = np.asarray(image, dtype=np.float32) / np.float32(255.0)
    pixels = (pixels - MEAN) / STD
    channels_first = pixels.transpose(2, 0, 1)
    batch = np.expand_dims(channels_first, axis=0)
    return np.ascontiguousarray(batch)


def classify_image(session, labels, image_path):
    """Run exact FRI inference and aggregate classes into two conditions."""
    tensor = prepare_image(image_path)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: tensor})
    output_tensor = outputs[0]
    logits = output_tensor[0]

    scores = logits.astype(np.float64) / TEMPERATURE
    scores = scores - scores.max()
    weights = np.exp(scores)
    probabilities = weights / weights.sum()
    healthy = np.array([name.lower().endswith("healthy") for name in labels])
    healthy_score = float(probabilities[healthy].sum())
    unhealthy_score = float(probabilities[~healthy].sum())
    condition = "healthy" if healthy_score > unhealthy_score else "unhealthy"
    return condition, healthy_score, unhealthy_score
