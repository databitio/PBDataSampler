# Match Type Filtering (Singles/Doubles)

**Type**: Feature
**Date**: 2026-02-15
**Status**: Complete

## Overview

Added the ability to filter PPA Tour YouTube videos by match type (singles, doubles, or both) before sampling frames. Classification is heuristic-based, using the presence of `/` in player names within video titles to distinguish doubles from singles.

## Problem/Goal

PPA Tour YouTube videos include both singles and doubles matches. Users need to sample frames from only one match type (e.g., only singles) to build focused training datasets for CVAT labeling. Previously, all match types were sampled indiscriminately.

## Solution/Implementation

A title-based heuristic classifies videos by splitting on a matchup separator and checking for `/` in player names (which indicates team pairings in doubles). The filter is applied after fetching the candidate pool but before the sampling loop.

- **Classification logic**: Split the title on a matchup separator. If either side (before context suffix on the right) contains `/`, classify as `"doubles"`. Otherwise `"singles"`. If no separator found, return `"unknown"`.
- **Recognised separators** (case-insensitive): `vs`, `vs.`, `v`, `takes on`, `against`, `faces`
- **Context stripping**: Tournament/venue suffixes are removed from the right side using patterns like `" at the "`, `" on Championship "`, `" in "` before checking for `/`.
- **Unknown handling**: Videos classified as `"unknown"` are kept (not excluded) to avoid silently dropping non-match content like highlights or compilations.
- **Traceability**: Each sample record in the manifest includes its classified `match_type`, and the overall `match_type` filter is recorded in manifest params.

## Code Changes

### Files Modified

- **`src/ppa_frame_sampler/config.py`** — Added `MatchType = Literal["singles", "doubles", "both"]` type alias and `match_type: MatchType = "both"` field to the `Config` dataclass (in the YouTube/catalog section).

- **`src/ppa_frame_sampler/youtube/models.py`** — Added `classify_match_type(title: str) -> str` function. Uses compiled `_VERSUS_RE` regex to split on matchup separators (`vs`, `vs.`, `v`, `takes on`, `against`, `faces`) and `_CONTEXT_RE` to strip tournament context (`at the`, `on Championship`, `in`). Checks for `/` in player names to detect doubles.

- **`src/ppa_frame_sampler/cli.py`** — Added `--match-type` CLI argument with choices `["singles", "doubles", "both"]` (default `"both"`), wired to `Config` constructor via `match_type=args.match_type`.

- **`src/ppa_frame_sampler/pipeline/collector.py`** — Added post-catalog filtering step using `classify_match_type()`, logging of filter results, `RuntimeError` if no candidates survive filtering, `match_type` in manifest params, and `match_type` field in each sample record via `_record_sample()`.

### Key Patterns

- Title parsing uses compiled regexes (`_VERSUS_RE`, `_CONTEXT_RE`) with `re.IGNORECASE` for robustness against case variations.
- Multiple separator patterns handle both current ("vs") and older ("takes on", "vs.", "against", "faces") PPA title formats.
- Context stripping removes tournament suffixes ("at the", "on Championship", "in") from the right side before checking for `/`.
- Filter is a list comprehension keeping entries matching the target type OR `"unknown"`.

## Key Decisions

- **Heuristic over metadata**: PPA Tour video titles follow a consistent naming convention, making title parsing reliable without needing YouTube API metadata or manual tagging.
- **Multiple separator patterns**: Older PPA videos (1-2+ years) use different title formats than recent ones (e.g., "takes on" instead of "vs"). Compiled regexes handle both eras.
- **Keep "unknown" videos**: Non-match videos (highlights, compilations) are not excluded when filtering, preventing silent data loss.
- **Filter placement**: Filtering happens after `list_recent_videos()` returns but before the sampling loop, so the candidate count in the manifest reflects the post-filter pool.
- **Default "both"**: No filtering by default, preserving backward compatibility.

## Tradeoffs

- **Pros**: Simple heuristic, no external dependencies, backward compatible, full traceability in manifest
- **Cons**: Heuristic depends on PPA Tour title conventions; unusual titles could be misclassified; "unknown" videos leak through when filtering (by design); new title formats may require adding more separator patterns

## Related Files

- `src/ppa_frame_sampler/config.py` — `MatchType` type alias and `Config.match_type` field
- `src/ppa_frame_sampler/youtube/models.py` — `classify_match_type()` classification function
- `src/ppa_frame_sampler/cli.py` — `--match-type` CLI argument
- `src/ppa_frame_sampler/pipeline/collector.py` — Filtering logic, manifest integration

## Testing / Verification

- [x] `classify_match_type()` smoke tests (doubles, singles, unknown, case-insensitive)
- [x] `Config(match_type=...)` field validation
- [x] `build_parser().parse_args(['--match-type', 'singles'])` CLI parsing
- [x] Existing test suite passes (pre-existing failures unrelated)
- [ ] Integration test: `--match-type singles` produces only singles in manifest
- [ ] Integration test: `--match-type doubles` produces only doubles in manifest

## Notes

- Title examples:
  - `"Johns/Tardio vs Shimabukuro/Funemizu at PPA Tour"` -> doubles
  - `"Hunter Johnson vs Christian Alshon at PPA Tour"` -> singles
  - `"Ben Johns takes on Federico Staksrud on Championship Sunday in Cincinnati!"` -> singles (older format)
  - `"PPA Tour Best Plays"` -> unknown
- If PPA Tour introduces new title formats, additional separator patterns may need to be added to `_VERSUS_RE`.
- The `_CONTEXT_RE` pattern strips context broadly — any occurrence of `" at the "`, `" on Championship "`, or `" in "` followed by text is treated as a suffix to remove.
