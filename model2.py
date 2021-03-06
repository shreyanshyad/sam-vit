from torch import einsum
from einops import rearrange
import torch
import torch.nn as nn
from torch.nn import *
import torch.nn.functional as F


class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-8):
        super().__init__()
        self.scale = dim ** -0.5
        self.eps = eps
        self.g = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        norm = torch.norm(x, dim=-1, keepdim=True) * self.scale
        return x / norm.clamp(min=self.eps) * self.g


class GLU(nn.Module):
    def __init__(self, dim_in, dim_out, activation):
        super().__init__()
        self.act = activation
        self.proj = nn.Linear(dim_in, dim_out * 2)

    def forward(self, x):
        x, gate = self.proj(x).chunk(2, dim=-1)
        return x * self.act(gate)


class PreNormWithDropPath(nn.Module):
    def __init__(self, dim, fn, drop_path_rate):
        super().__init__()
        self.norm = RMSNorm(dim)
        self.fn = fn
        self.drop_path = DropPath(drop_path_rate)

    def forward(self, x, **kwargs):
        return self.drop_path(self.fn(self.norm(x)))


class FeedForward(nn.Module):
    def __init__(self, dim, hidden_dim, dropout):
        super().__init__()
        self.net = nn.Sequential(
            GLU(dim, hidden_dim, nn.SiLU()),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, dim),
            nn.Dropout(dropout)
        )

    def forward(self, x):
        return self.net(x)


def drop_path(x, drop_prob: float = 0., training: bool = False):
    if drop_prob == 0. or not training:
        return x
    keep_prob = 1 - drop_prob
    shape = (x.shape[0],) + (1,) * (x.ndim - 1)
    random_tensor = keep_prob + \
        torch.rand(shape, dtype=x.dtype, device=x.device)
    random_tensor.floor_()  # binarize
    output = x.div(keep_prob) * random_tensor
    return output


class DropPath(nn.Module):
    """
    Obtained from: github.com:rwightman/pytorch-image-models
    Drop paths (Stochastic Depth) per sample  (when applied in main path of residual blocks).
    """

    def __init__(self, drop_prob=None):
        super(DropPath, self).__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        return drop_path(x, self.drop_prob, self.training)


class Attention(Module):
    """
    Obtained from timm: github.com:rwightman/pytorch-image-models
    """

    def __init__(self, dim, num_heads, attention_dropout=0.1, projection_dropout=0.1):
        super().__init__()
        self.num_heads = num_heads
        head_dim = dim // self.num_heads
        self.scale = head_dim ** -0.5

        self.qkv = Linear(dim, dim * 3, bias=False)
        self.attn_drop = Dropout(attention_dropout)
        self.proj = Linear(dim, dim)
        self.proj_drop = Dropout(projection_dropout)

    def forward(self, x):
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, C //
                                  self.num_heads).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]

        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x

# def exists(val):
#     return val is not None


# class Attention(nn.Module):
#     def __init__(self, dim, heads, dim_head=64, dropout=0.):
#         super().__init__()
#         inner_dim = dim_head * heads
#         self.heads = heads
#         self.scale = dim_head ** -0.5

#         self.to_q = nn.Linear(dim, inner_dim, bias=False)
#         self.to_kv = nn.Linear(dim, inner_dim * 2, bias=False)

#         self.attend = nn.Softmax(dim=-1)
#         self.dropout = nn.Dropout(dropout)

#         self.mix_heads_pre_attn = nn.Parameter(torch.randn(heads, heads))
#         self.mix_heads_post_attn = nn.Parameter(torch.randn(heads, heads))

#         self.to_out = nn.Sequential(
#             nn.Linear(inner_dim, dim),
#             nn.Dropout(dropout)
#         )

#     def forward(self, x, context=None):
#         b, n, _, h = *x.shape, self.heads

#         context = x if not exists(context) else torch.cat((x, context), dim=1)

#         qkv = (self.to_q(x), *self.to_kv(context).chunk(2, dim=-1))
#         q, k, v = map(lambda t: rearrange(t, 'b n (h d) -> b h n d', h=h), qkv)

#         dots = einsum('b h i d, b h j d -> b h i j', q, k) * self.scale

#         # talking heads, pre-softmax
#         dots = einsum('b h i j, h g -> b g i j', dots, self.mix_heads_pre_attn)

#         attn = self.attend(dots)
#         attn = self.dropout(attn)

#         # talking heads, post-softmax
#         attn = einsum('b h i j, h g -> b g i j',
#                       attn, self.mix_heads_post_attn)

#         out = einsum('b h i j, b h j d -> b h i d', attn, v)
#         out = rearrange(out, 'b h n d -> b n (h d)')
#         return self.to_out(out)

# class Attention(nn.Module):
#     def __init__(self, dim, heads, dim_head=64, dropout=0.):
#         super().__init__()
#         inner_dim = dim_head * heads
#         self.heads = heads
#         self.temperature = nn.Parameter(
#             torch.log(torch.tensor(dim_head ** -0.5)))

#         self.attend = nn.Softmax(dim=-1)
#         self.dropout = nn.Dropout(dropout)

#         self.to_qkv = nn.Linear(dim, inner_dim * 3, bias=False)

#         self.to_out = nn.Sequential(
#             nn.Linear(inner_dim, dim),
#             nn.Dropout(dropout)
#         )

#     def forward(self, x):
#         qkv = self.to_qkv(x).chunk(3, dim=-1)
#         q, k, v = map(lambda t: rearrange(
#             t, 'b n (h d) -> b h n d', h=self.heads), qkv)

#         dots = torch.matmul(q, k.transpose(-1, -2)) * self.temperature.exp()

#         mask = torch.eye(dots.shape[-1], device=dots.device, dtype=torch.bool)
#         mask_value = -torch.finfo(dots.dtype).max
#         dots = dots.masked_fill(mask, mask_value)

#         attn = self.attend(dots)
#         attn = self.dropout(attn)

#         out = torch.matmul(attn, v)
#         out = rearrange(out, 'b h n d -> b n (h d)')
#         return self.to_out(out)


class Transformer(nn.Module):
    def __init__(self, embedding_dim, depth, heads, mlp_dim,
                 dropout, stochastic_depth=0.1):
        super().__init__()
        self.layers = nn.ModuleList([])

        dpr = [x.item() for x in torch.linspace(
            0, stochastic_depth, depth)]

        for i in range(depth):
            self.layers.append(nn.ModuleList([
                PreNormWithDropPath(embedding_dim, Attention(
                    dim=embedding_dim, num_heads=heads), drop_path_rate=dpr[i]),
                PreNormWithDropPath(embedding_dim, FeedForward(
                    dim=embedding_dim, hidden_dim=mlp_dim, dropout=dropout), drop_path_rate=dpr[i])
            ]))

    def forward(self, x):
        for attn, ff in self.layers:
            x = attn(x) + x
            x = ff(x) + x
        return x


class Tokenizer(nn.Module):
    def __init__(self,
                 n_input_channels,
                 n_output_channels,
                 ):    # filter size for in between convolutions
        super(Tokenizer, self).__init__()

        n_conv_layers = 2
        kernel_size = 3
        stride = max(
            1, (kernel_size // 2) - 1)
        padding = max(
            1, (kernel_size // 2))
        pooling_kernel_size = 3
        pooling_stride = 2
        pooling_padding = 1

        n_filter_list = [n_input_channels]+[64]+[n_output_channels]

        # first layer, middle ones of same n_conv_layers-2 times, last layer

        self.conv_layers = nn.Sequential(
            nn.Conv2d(n_filter_list[0], n_filter_list[1],
                      kernel_size=(3, 3),
                      stride=(stride, stride),
                      padding=(padding, padding),
                      bias=False
                      ),
            nn.ReLU(),  # activation
            nn.MaxPool2d(kernel_size=pooling_kernel_size,
                         stride=pooling_stride,
                         padding=pooling_padding),
            nn.Conv2d(n_filter_list[1], n_filter_list[2],
                      kernel_size=(1, 1),
                      stride=(stride, stride),
                      padding=(padding, padding),
                      bias=False
                      ),
            nn.ReLU(),  # activation
            nn.MaxPool2d(kernel_size=pooling_kernel_size,
                         stride=pooling_stride,
                         padding=pooling_padding)
        )

        self.flattener = nn.Flatten(2, 3)
        self.apply(self.init_weight)

    def sequence_length(self, n_channels, height, width):
        return self.forward(torch.zeros((1, n_channels, height, width))).shape[1]

    def forward(self, x):
        return self.flattener(self.conv_layers(x)).transpose(-2, -1)

    @staticmethod
    def init_weight(m):
        if isinstance(m, nn.Conv2d):
            nn.init.kaiming_normal_(m.weight)

# For image size 32
# keep embedding (word) dim as 128
# layer=2
# mlp ratio 1
# num heads 2
# n conv layers 2


class CCT(nn.Module):
    def __init__(self,
                 img_size,
                 embedding_dim,
                 num_layers,
                 num_heads,
                 mlp_ratio,
                 num_classes,
                 n_input_channels=3,    # 3 for images
                 dropout=0.1,
                 *args, **kwargs):
        super(CCT, self).__init__()

        self.tokenizer = Tokenizer(n_input_channels=n_input_channels,
                                   n_output_channels=embedding_dim)

        self.transformer = Transformer(
            embedding_dim=embedding_dim, depth=num_layers,
            heads=num_heads,
            mlp_dim=int(embedding_dim * mlp_ratio),
            dropout=dropout)

        seq_len = self.tokenizer.sequence_length(
            n_input_channels, img_size, img_size)

        self.positional_emb = Parameter(torch.zeros(1, seq_len, embedding_dim),
                                        requires_grad=True)
        init.trunc_normal_(self.positional_emb, std=0.2)

        self.dropout = Dropout(p=dropout)

        # self.mlp_head = nn.Sequential(
        #     RMSNorm(dim),
        #     nn.Linear(dim, num_classes)
        # )
        # these two below are for same task commented above
        self.norm = RMSNorm(embedding_dim)
        self.fc = Linear(embedding_dim, num_classes)

        self.attention_pool = Linear(embedding_dim, 1)
        # weights for different layers, how to pool

        # settng weights
        self.apply(self.init_weight)

    def forward(self, x):
        x = self.tokenizer(x)
        x += self.positional_emb
        x = self.dropout(x)
        x = self.transformer(x)

        x = self.norm(x)
        x = torch.matmul(F.softmax(self.attention_pool(
            x), dim=1).transpose(-1, -2), x).squeeze(-2)
        x = self.fc(x)

        return x

    @staticmethod
    def init_weight(m):
        if isinstance(m, Linear):
            init.trunc_normal_(m.weight, std=.02)
            if isinstance(m, Linear) and m.bias is not None:
                init.constant_(m.bias, 0)
        elif isinstance(m, LayerNorm):
            init.constant_(m.bias, 0)
            init.constant_(m.weight, 1.0)
