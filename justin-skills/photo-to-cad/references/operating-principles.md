# Operating principles for reverse engineering

How to run the engagement so the model converges on the object, not just on a plausible
shape. These are general and apply to any part.

## 1. Done means four things

1. **It matches the object** in the matched renders, with the critical dimensions confirmed
   by calipers or a drawing.
2. **It works:** it mates with what it mates with, prints, and meets the minimum features at
   the final scale.
3. **It rebuilds from the parameter block** alone (`<part>_model.py`), and any Fusion script
   is generated from that same block.
4. **It stays editable:** the parameters the user will want to tweak are named, bounded and
   derived correctly.

## 2. One source of truth

`P` in `<part>_model.py` is the source. The CadQuery solid, STEP, STL, renders and the
Fusion script are products of it. Generate the Fusion script from `P`; never hand-copy
numbers into it. When any second implementation exists (a preview, a Fusion port),
parity-test it against the CadQuery build.

## 3. Resolve uncertainty in layers, in order

| Layer | Evidence | Can a metric check it? |
|---|---|---|
| Topology (what connects to what, which way it bends or folds, what's hollow) | a confirmed diagram, a user sketch, a second view | no |
| Proportion | a rectified or matched view, silhouettes, markers | yes |
| Dimension | a scale reference, calipers, nominals | yes |
| Tolerance / fit | the mating part, a test print | yes |

Classify every correction by layer. A topology correction invalidates proportion work built
on the old topology.

## 4. The loop breaker

"Build anyway" is right for proportion and dimension. It's wrong to keep building once
topology is in dispute. **Two corrections on the same feature means stop building it and
change the channel:**
1. show your reading as a numbered traced path on the photo plus a side profile;
2. ask for the user's sketch or colored strokes on the photo;
3. ask for a second photo from the angle that shows the ambiguity;
4. matched renders, or markers the user places.

A third guess in the same channel is usually wrong in the same way.

## 5. Evidence with every claim

"Matches", "fixed" and "fits" each need, in the same message, a viewed render (matched,
where a camera is solved) or a number against a threshold. Rule out the measurement before
blaming the model: perspective, a macro shot's depth, a mis-solved camera, or a stale
render.

## 6. The user's words and a decision log

Name parameters in the user's terms. Keep a short log in the working directory: the decisions
and the user's corrections **verbatim**, with rev labels. When corrections conflict,
reconcile them out loud; they usually describe different parts of the same feature. When the
user says something doesn't matter, stop optimizing for it, and don't reintroduce it.

## 7. Continuity

Keep `session_state.md` beside the model:
- current rev and files;
- the dimension table with sources and confidence;
- open questions;
- the decision log;
- the next action.

A new session should resume from it without the chat history.

## 8. Improve the skill

Any surprise (a trap, a failed pattern, a new check) goes into the references at the end of
the session, generalized. When a new failure mode appears, add a case to `evals/evals.json`.
