# Removing "icon not available"

Home Assistant and HACS both fetch the picture next to an integration from
`brands.home-assistant.io`, which is served from the
[home-assistant/brands](https://github.com/home-assistant/brands) repository.
Custom integrations that have no entry there show a placeholder reading "icon not
available". It is purely cosmetic -- nothing about the integration is broken --
but it is also the first thing anyone sees when browsing HACS.

The images are already generated in `brands/custom_integrations/poolsmart/`.

## What to submit

| File | Size | Purpose |
|---|---|---|
| `icon.png` | 256×256 | Integration tile, HACS list |
| `icon@2x.png` | 512×512 | High-DPI screens |
| `logo.png` | 1024×256 | Integration page header |
| `logo@2x.png` | 2048×512 | High-DPI screens |

All four have transparent backgrounds and no padding, which the brands
repository requires.

## Steps

1. Fork <https://github.com/home-assistant/brands>.
2. Copy the four files into `custom_integrations/poolsmart/` in your fork. The
   directory name must match the integration domain exactly.
3. Commit and open a pull request titled `Add PoolSmart`.
4. Wait for it to be merged. Review usually takes a few days.

Once merged, the placeholder is replaced automatically. No change to the
integration is needed and no update has to be installed -- Home Assistant fetches
the image from the CDN at display time.

## Regenerating the images

```bash
python3 tools/make_brand_images.py
```

Requires Pillow. Editing the colours or the shape at the top of that script and
re-running it produces a matching set at all four sizes, so the design stays
consistent across them.

## Why not ship the icon inside the integration

Home Assistant deliberately does not read brand images out of a custom component
directory. Serving them centrally means the frontend can cache them, and it keeps
one integration from shipping an image that impersonates another. The trade is
that a new custom integration always starts with the placeholder.
