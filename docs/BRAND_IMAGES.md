# Brand images

Since Home Assistant 2026.3 a custom integration carries its own brand images.
They live in `custom_components/poolsmart/brand/` and Home Assistant serves them
from `/api/brands/integration/poolsmart/{image}`. Local images take priority over
the CDN, and no submission anywhere is required — the `home-assistant/brands`
repository now auto-closes pull requests for custom integrations and points
contributors at this mechanism instead.

## What ships

| File | Size | Used for |
|---|---|---|
| `icon.png` | 256×256 | Integration tile, device pages |
| `icon@2x.png` | 512×512 | High-DPI screens |
| `logo.png` | 927×256 | Integration page header |
| `logo@2x.png` | 1859×512 | High-DPI screens |
| `dark_*.png` | same | Dark themes; the wordmark is light instead of navy |

All have transparent backgrounds and no padding.

## Where you will and will not see them

**Settings → Devices & services**: the icon appears. This is the endpoint Home
Assistant itself uses.

**HACS**: still shows "icon not available". This is a known bug in the HACS
frontend, not in this integration — HACS pins an older copy of the Home Assistant
frontend whose `brandsUrl()` helper still points at the public CDN rather than
the local proxy, so it never asks Home Assistant for the inline image. Tracked as
[hacs/integration#5223](https://github.com/hacs/integration/issues/5223) and
[#5171](https://github.com/hacs/integration/issues/5171). It will resolve itself
when HACS ships a rebuilt frontend bundle; nothing here needs changing.

If the icon does not appear in Home Assistant either, check that you are on
2026.3 or newer, and clear the browser cache — the proxy caches images on disk
and the browser caches them again.

## Regenerating

```bash
python3 tools/make_brand_images.py
```

Requires Pillow. The colours and shapes are defined at the top of that script;
editing them and re-running produces a matching set at every size and in both
themes, so the design cannot drift between files.
