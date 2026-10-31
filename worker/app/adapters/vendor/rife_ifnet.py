"""IFNet of Practical-RIFE 4.25.

Spec: specs/03-tech-stack.md#worker-python-312

Copied from train_log/IFNet_HDv3.py and model/warplayer.py of Practical-RIFE, MIT, see
LICENSE-Practical-RIFE, with the half precision warp of vs-rife, MIT, see LICENSE-vs-rife.
Reduced to inference and typed. The layout must keep matching the published weights.
"""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional

LEAK = 0.2
FLOW_BLOCKS = 5


def _conv(in_planes: int, out_planes: int, stride: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_planes, out_planes, 3, stride, 1), nn.LeakyReLU(LEAK, inplace=True)
    )


def _resize(x: Tensor, factor: float) -> Tensor:
    return functional.interpolate(x, scale_factor=factor, mode="bilinear", align_corners=False)


class Head(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.cnn0 = nn.Conv2d(3, 16, 3, 2, 1)
        self.cnn1 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn2 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(16, 4, 4, 2, 1)
        self.relu = nn.LeakyReLU(LEAK, inplace=True)

    def forward(self, x: Tensor) -> Tensor:
        x = self.relu(self.cnn0(x))
        x = self.relu(self.cnn1(x))
        x = self.relu(self.cnn2(x))
        result: Tensor = self.cnn3(x)
        return result


class ResConv(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.conv = nn.Conv2d(channels, channels, 3, 1, 1)
        self.beta = nn.Parameter(torch.ones((1, channels, 1, 1)))
        self.relu = nn.LeakyReLU(LEAK, inplace=True)

    def forward(self, x: Tensor) -> Tensor:
        result: Tensor = self.relu(self.conv(x) * self.beta + x)
        return result


class IFBlock(nn.Module):
    def __init__(self, in_planes: int, channels: int) -> None:
        super().__init__()
        self.conv0 = nn.Sequential(
            _conv(in_planes, channels // 2, 2), _conv(channels // 2, channels, 2)
        )
        self.convblock = nn.Sequential(*(ResConv(channels) for _ in range(8)))
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(channels, 4 * 13, 4, 2, 1), nn.PixelShuffle(2)
        )

    def forward(
        self, x: Tensor, flow: Tensor | None, scale: float
    ) -> tuple[Tensor, Tensor, Tensor]:
        x = _resize(x, 1.0 / scale)
        if flow is not None:
            x = torch.cat((x, _resize(flow, 1.0 / scale) / scale), 1)
        out = _resize(self.lastconv(self.convblock(self.conv0(x))), scale)
        return out[:, :4] * scale, out[:, 4:5], out[:, 5:]


def _warp(image: Tensor, flow: Tensor, grid: Tensor, divisor: Tensor) -> Tensor:
    """grid_sample has no half precision version, so it always runs in float32."""
    sample = (grid + flow.to(torch.float) / divisor).permute(0, 2, 3, 1)
    warped = functional.grid_sample(
        image.to(torch.float), sample, mode="bilinear", padding_mode="border", align_corners=True
    )
    return warped.to(image.dtype)


def _pixel_grid(like: Tensor) -> tuple[Tensor, Tensor]:
    """The identity sampling grid, and what turns pixels of flow into grid units."""
    height, width = like.shape[2:]
    y, x = torch.meshgrid(
        torch.linspace(-1.0, 1.0, height, device=like.device),
        torch.linspace(-1.0, 1.0, width, device=like.device),
        indexing="ij",
    )
    divisor = torch.tensor([(width - 1) / 2, (height - 1) / 2], device=like.device)
    return torch.stack((x, y)).unsqueeze(0), divisor.view(1, 2, 1, 1)


class IFNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.block0 = IFBlock(7 + 8, 192)
        self.block1 = IFBlock(8 + 4 + 8 + 8, 128)
        self.block2 = IFBlock(8 + 4 + 8 + 8, 96)
        self.block3 = IFBlock(8 + 4 + 8 + 8, 64)
        self.block4 = IFBlock(8 + 4 + 8 + 8, 32)
        self.encode = Head()

    def forward(self, img0: Tensor, img1: Tensor, time: float, scale: float) -> Tensor:
        """The frame at time (0 to 1) between img0 and img1. Sides must fit 64 / min(scale, 1)."""
        timestep = torch.full_like(img0[:, :1], time)
        grid, divisor = _pixel_grid(img0)
        f0 = self.encode(img0)
        f1 = self.encode(img1)
        blocks = (self.block0, self.block1, self.block2, self.block3, self.block4)
        scales = [2.0 ** (FLOW_BLOCKS - 1 - index) / scale for index in range(FLOW_BLOCKS)]

        flow, mask, feat = blocks[0](torch.cat((img0, img1, f0, f1, timestep), 1), None, scales[0])
        warped0 = _warp(img0, flow[:, :2], grid, divisor)
        warped1 = _warp(img1, flow[:, 2:4], grid, divisor)
        for block, block_scale in zip(blocks[1:], scales[1:], strict=True):
            wf0 = _warp(f0, flow[:, :2], grid, divisor)
            wf1 = _warp(f1, flow[:, 2:4], grid, divisor)
            features = torch.cat((warped0, warped1, wf0, wf1, timestep, mask, feat), 1)
            delta, mask, feat = block(features, flow, block_scale)
            flow = flow + delta
            warped0 = _warp(img0, flow[:, :2], grid, divisor)
            warped1 = _warp(img1, flow[:, 2:4], grid, divisor)
        weight = torch.sigmoid(mask)
        return warped0 * weight + warped1 * (1 - weight)
