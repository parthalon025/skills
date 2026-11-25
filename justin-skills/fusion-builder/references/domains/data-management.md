# Data panel and version management

Single-user cloud data on personal use: projects, folders, files, version history, public
shared links, comments and markup. No multi-user management, no branching or merging, and a
hard cap of **10 active editable documents**.

That cap is the defining constraint of the free tier and the thing most likely to interrupt a
build session. Know where the user stands before starting something new.

## Reading the data structure

The MCP gives you the cheap paths directly:

```
fusion_mcp_read{queryType:"projects"}                          list projects
fusion_mcp_read{queryType:"document", operation:"search", name:"clip"}
fusion_mcp_read{queryType:"document", operation:"recent"}
fusion_mcp_read{queryType:"document", operation:"open"}         currently open docs
fusion_mcp_execute{featureType:"document", object:{operation:"open", fileId:"..."}}
```

Use those before writing a script. For anything deeper — versions, folder trees, save
descriptions — go through `app.data`:

```python
import adsk.core, adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    df = doc.dataFile
    if not df:
        print("document has never been saved - no dataFile yet")
        return
    print("name       : %s" % df.name)
    print("project    : %s" % df.parentProject.name)
    print("folder     : %s" % df.parentFolder.name)
    print("version    : v%d (latest v%d)" % (df.versionNumber, df.latestVersion.versionNumber))
    print("versions   : %d" % df.versions.count)
    for i in range(min(df.versions.count, 10)):
        v = df.versions.item(i)
        print("  v%-3d %s  %s" % (v.versionNumber, v.dateCreated, (v.description or "").strip()[:60]))
```

`dataFile` is `None` for an unsaved document. Check it — a lot of scripts blow up on exactly
this, mid-session, on the one document the user hadn't saved yet.

## Version history

Every save creates a version, and the save description becomes the version comment. Unlabeled
versions are the reason nobody can find the good one three weeks later.

**So: propose a description at every save gate.** Not "update" — say what changed:
`"bore 6.0 -> 6.2, added print clearance param"`. One line, present it as part of the G7 ask:

```
Ready to save as v7 with: "taper shortened to 60% of length, matches reference photo"
Save?
```

Saving is a G7 action and never happens without an instruction. Restoring or promoting an old
version is likewise the user's call — describe what the versions contain and let them pick.

Version history is also the honest answer to "can you undo all of that?" when the timeline
undo won't reach. If the last good state was a saved version, say which one and what it
contains, rather than trying to reverse-engineer the geometry back.

## The 10-document cap

Personal use allows 10 active, editable documents. Beyond that, files stay in the cloud but
go read-only until something is archived or the license changes.

What to do when the user is near the cap:

1. **Report it, don't discover it mid-build.** If creating a new document is part of the plan,
   check the count at G0 and say where they stand.
2. **Archive completed projects**, don't delete them. Archived files remain in the cloud.
3. **Export an F3D before archiving anything** they might want back — it's the lossless local
   copy, and the one format personal use definitely supports.
4. **Fewer documents, more components.** A multi-part assembly can live in one document with
   several components instead of one document per part. That's usually the better model
   anyway, and on the free tier it's the difference between fitting and not.

Don't turn a cap into an upsell. Name the limit, give the workaround, move on.

## Working within one document

Given the cap, prefer:

- One document per *project*, components inside it.
- Derived/linked components across documents cost a document each — use sparingly.
- Bodies for throwaway variants, components for real parts.

## Shared views

Personal use includes public shared views — a browser link to a read-only 3D view, useful for
getting a second opinion on a part. There's no shared-view *collaboration* (comment threads
tied to the model) on the free tier, and no multi-user permissions.

Creating a shared link publishes the model publicly to anyone with the URL. Treat it as a
publish action: describe what it does, and wait for an explicit yes.

## Housekeeping report

Worth running when a session starts on an unfamiliar workspace:

```
Project      : Fishing gear (14 files)
Active doc   : Clip_H2D  v6, last saved 2026-09-14
Unsaved      : yes - 3 features since last save
Documents    : 9 of 10 active  <- one away from the cap
Suggestion   : Clip_v2_old looks superseded; export F3D and archive it before the next new doc
```

Facts, then one suggestion. Archiving is their decision and their click.
