"""Décodage YOLO/ONNX, tuiles et NMS avec un faux modèle ONNX à sortie fixe."""

import numpy as np
import pytest

onnx = pytest.importorskip("onnx")
from onnx import TensorProto, helper  # noqa: E402

from fccoach.vision.detector import YoloOnnxDetector  # noqa: E402


def fake_yolo(path, names: dict[int, str]) -> None:
    """Sortie (1, 4+nc, 2) : une boîte « player » à (100,100) 40x80, une boîte faible."""
    nc = len(names)
    out = np.zeros((1, 4 + nc, 2), np.float32)
    out[0, :4, 0] = [100, 100, 40, 80]
    out[0, 4, 0] = 0.9
    out[0, :4, 1] = [300, 300, 10, 10]
    out[0, 4 + nc - 1, 1] = 0.1          # sous le seuil
    const = helper.make_tensor("c", TensorProto.FLOAT, out.shape, out.flatten())
    nodes = [
        helper.make_node("ReduceSum", ["images"], ["s"], keepdims=0),
        helper.make_node("Mul", ["s", "zero"], ["z"]),
        helper.make_node("Add", ["c", "z"], ["output0"]),
    ]
    graph = helper.make_graph(
        nodes, "fake",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 640, 640])],
        [helper.make_tensor_value_info("output0", TensorProto.FLOAT, list(out.shape))],
        initializer=[const, helper.make_tensor("zero", TensorProto.FLOAT, [], [0.0])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    helper.set_model_props(model, {"names": str(names)})
    onnx.save(model, str(path))


def test_tiles_decode_and_offsets(tmp_path):
    p = tmp_path / "m.onnx"
    fake_yolo(p, {0: "player", 1: "goalkeeper", 2: "referee", 3: "ball"})
    det = YoloOnnxDetector(p, ["CPUExecutionProvider"], mode="tiles", tile_size=640, tile_overlap=96)
    dets = det.detect(np.zeros((1080, 1920, 3), np.uint8))
    # Une boîte par tuile (8 tuiles), décalée de l'origine de chaque tuile
    assert len(dets) == 8
    assert all(d.cls == "player" for d in dets)
    xs = sorted({round(d.x1) for d in dets})
    assert xs == [80, 624, 1168, 1360]


def test_coco_fallback_mapping(tmp_path):
    p = tmp_path / "coco.onnx"
    names = {i: f"c{i}" for i in range(80)}
    names[0], names[32] = "person", "sports ball"
    fake_yolo(p, names)
    det = YoloOnnxDetector(p, ["CPUExecutionProvider"])
    assert det.class_map == {0: "player", 32: "ball"}
    assert det.detect(np.zeros((640, 640, 3), np.uint8))[0].cls == "player"
