"""SRVGGNetCompact, the network of realesr-general-x4v3.

Spec: specs/03-tech-stack.md#worker-python-312

Copied from Real-ESRGAN (realesrgan/archs/srvgg_arch.py), BSD-3-Clause, see LICENSE-Real-ESRGAN.
Reduced to the prelu variant and typed. The layout must keep matching the published weights.
"""

from __future__ import annotations

from torch import Tensor, nn
from torch.nn import functional

KERNEL = 3


class SrVggNetCompact(nn.Module):
    """Upsamples only in the last layer and learns the residual over a nearest upscale."""

    def __init__(self, num_feat: int, num_conv: int, upscale: int) -> None:
        super().__init__()
        self.upscale = upscale
        self.body = nn.ModuleList([nn.Conv2d(3, num_feat, KERNEL, 1, 1), nn.PReLU(num_feat)])
        for _ in range(num_conv):
            self.body.append(nn.Conv2d(num_feat, num_feat, KERNEL, 1, 1))
            self.body.append(nn.PReLU(num_feat))
        self.body.append(nn.Conv2d(num_feat, 3 * upscale * upscale, KERNEL, 1, 1))
        self.upsampler = nn.PixelShuffle(upscale)

    def forward(self, x: Tensor) -> Tensor:
        out = x
        for layer in self.body:
            out = layer(out)
        out = self.upsampler(out)
        result: Tensor = out + functional.interpolate(x, scale_factor=self.upscale, mode="nearest")
        return result
