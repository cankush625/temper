"""Lifecycle: archive learned skills that are not earning their place.

Run once per session start, per layer. A skill's *rate* is its loads (Skill tool calls) over
the requests that reached its layer since it was created — so it ages with use of the tool,
not with wall time, and a week away from the keyboard ages nothing.

  - Probation: until `maturity` requests have passed since creation, a skill is never
    archived and does not count against capacity.
  - Graduation: at maturity, a skill that was never loaded is archived. No use across a full
    probation is the evidence; anything less is not.
  - Capacity: once a layer holds more than `capacity` mature skills, the lowest rates are
    archived until it fits.

Archiving moves the folder out of recall (lib/skill_store.archive); it never deletes.
"""

from __future__ import annotations

from pathlib import Path

from . import learn_state, skill_store


def _age(skill: skill_store.Skill, requests: int) -> int:
    return max(0, requests - int(skill.meta.get("created_requests", 0) or 0))


def plan(skills: list[skill_store.Skill], requests: int, maturity: int,
         capacity: int) -> list[tuple[skill_store.Skill, str]]:
    """
    Which skills to archive and why, without touching disk.

    Example:
        >>> plan([], requests=500, maturity=100, capacity=50)
        []
    """

    out = []
    mature = []
    for s in skills:
        age = _age(s, requests)
        if age < maturity:
            continue
        uses = int(s.meta.get("uses", 0) or 0)
        if uses == 0:
            out.append((s, f"never loaded in {age} requests of probation"))
        else:
            mature.append((uses / age, s))
    mature.sort(key=lambda pair: pair[0])
    excess = len(mature) - capacity
    for rate, s in mature[:max(0, excess)]:
        out.append((s, f"over capacity ({capacity}); lowest load rate {rate:.3f}"))
    return out


def run(project_root: str | Path, settings: dict) -> list[dict]:
    """
    Apply the lifecycle to each enabled layer; return what was archived.

    Example:
        >>> run(root, config.learn(cfg))  # doctest: +SKIP
        [{'name': 'tl-old-trick', 'layer': 'project', 'reason': 'never loaded in 120 requests ...'}]
    """

    archived = []
    layers = skill_store.LAYERS if settings["global"] else ("project",)
    for layer in layers:
        skills = skill_store.managed(project_root, (layer,))
        if not skills:
            continue
        doomed = plan(skills, learn_state.requests(layer, project_root),
                      settings[f"maturity_{layer}"], settings[f"capacity_{layer}"])
        for skill, reason in doomed:
            skill_store.archive(skill, project_root, {"action": "archive", "absorbed_into": "",
                                                       "reason": reason, "run": "lifecycle"})
            archived.append({"name": skill.name, "layer": layer, "reason": reason})
    return archived
