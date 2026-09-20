# Vendor source patches

Prefer an in-process `logic_mcp.instruments` plugin, or a standalone process that already speaks [`logic_mcp.instrument.v1`](../src/logic_mcp/instrument/PROTOCOL.md).

When that is not enough and **upstream GUI / SDK source must be patched**, keep the delta here. Do not vendor a full copy of the other project.

## Layout

```text
vendor/<id>/
  README.md          # why, how to apply, license
  upstream.yaml      # clone URL + exact commit the patch was made against
  series             # patch files in apply order (one name per line)
  0001-….patch
```

`<id>` matches the MCP backend id (`dsview`, later `saleae`, …).

## Adding another vendor

1. Clone their tree, check out a **pinned commit**, make the smallest change that implements `logic_mcp.instrument.v1` (or documents why a thinner hook is enough).
2. From that tree:

   ```bash
   git add -- the files you touched
   git diff --cached --no-color --no-ext-diff > /path/to/logic-mcp/vendor/<id>/0001-logic-mcp-instrument-ipc.patch
   git restore --staged -- .
   ```

3. Write `upstream.yaml` and `series`. Record the **upstream license**. Patches that contain their source stay under that license; this repo’s MIT license does not relicense them.
4. Link the directory from the top-level README.

Apply (from the vendor’s source root, at the recorded commit):

```bash
while IFS= read -r p; do
  [ -z "$p" ] || [ "${p#\#}" != "$p" ] && continue
  git apply "/path/to/logic-mcp/vendor/<id>/$p"
done < "/path/to/logic-mcp/vendor/<id>/series"
```
