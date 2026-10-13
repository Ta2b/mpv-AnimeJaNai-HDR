#!/usr/bin/env python3
"""Names the two free dimensions of a RIFE model "height" and "width".

The RIFE models of the project leave the picture size free without naming it. The engine can
then not tell ONNX Runtime the size it will use, and Core ML only takes models whose input
size is known. Nothing else changes: same nodes, same weights.

usage: name_rife_dims.py INPUT.onnx OUTPUT.onnx
"""
import sys

import onnx


def main():
    source, target = sys.argv[1], sys.argv[2]
    model = onnx.load(source)
    values = list(model.graph.input) + list(model.graph.output)
    assert len(model.graph.input) == 1, 'one input expected'
    for value in values:
        dims = value.type.tensor_type.shape.dim
        assert len(dims) == 4, f'{value.name}: four dimensions expected'
        for dim, name in ((dims[2], 'height'), (dims[3], 'width')):
            if dim.HasField('dim_value') and dim.dim_value > 0:
                raise SystemExit(f'{source}: {value.name} already has a fixed size')
            dim.Clear()
            dim.dim_param = name
    onnx.save(model, target)
    print(f'{target}: height and width named')


if __name__ == '__main__':
    main()
