# Tactical replay format notes

Investigated 2026-11-18 against local ACE COMBAT 8 executable build 26002268 (Steam app 2288340), and 19 existing `SavedVersion=32` saves. All binary scalars below are little-endian. This is a reverse-engineered layout for this version, not an official format specification.

## What is established

The postmission tactical replay is driven by saved object telemetry. Native debriefing actors consume a replay data manager; icons are meshes and their trail uses `NS_DebriefingRibbon`. It is not a pre-rendered movie or a collection of sprite frames. A web viewer can consume the telemetry without recreating the full game engine.

Static native inspection identifies the active object hash-table traversal and selection flags, and asset inspection identifies the debriefing icon/ribbon classes. Binary parsing and structural validation independently agree across all 19 saves. State meanings and some event meanings below are correlations, explicitly separated from structural fields.

## Outer save and compression

The file begins with Unreal `GVAS`. `ac8_replay.py` locates the `ReplayFileHeader` tagged property and parses the following property list, rather than hard-coding the variable-sized GVAS preamble. FString uses signed int32 length including the terminator: positive UTF-8 byte count, negative UTF-16LE code-unit count.

Modern complete property tags contain FString name; a recursive type name tree (FString name, uint32 child count, children); uint32 serialized payload size; uint8 flags; optional uint32 array index (flag 1); optional 16-byte property GUID (flag 2); then the payload. `None` ends a property list. Flag 8 indicates native serialization, flag 16 carries a true Boolean, flag 32 is accepted; extension flag 4 is unsupported. The parser only implements the property shapes needed here. See the [CUE4Parse property-tag implementation](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Objects/FPropertyTag.cs) for broader UE context.

Relevant outer properties: `ReplayFileHeader`, `BufferSize`, `BufferFrontSize`, `BufferBackSize`, `bBufferCompressed`, `UncompressedBufferSize`, `Buffer`, `SavedVersion`. `Buffer` is a byte array with uint32 count preceding its bytes. Compressed buffers in these saves use a **raw LZ4 block**, without an LZ4 frame header. The supplied decoder checks match references, bounds and exact decoded length.

`ReplayFileHeader` includes MissionID, LevelId, MapPath, GameDifficulty, TotalReplayTime, player plane information and other metadata. Preserve `MapPath`: mission IDs do not always equal physical mission-folder numbers. The converter exports selected mission metadata, not every header field; `--inspect` retains the parsed header.

## Decoded buffer and virtual addresses

Decoded bytes comprise a front record region, a compacted back record region, and a trailing tagged `LiveReplaySystemSaveGame` section. The trailing section includes `StringList` and `NamedHashToIDMap`; these are available through inspection.

At byte zero the 16-byte buffer header contains four uint32 values:

| Offset | Meaning |
| --- | --- |
| 0 | Front end, matching BufferFrontSize |
| 4 | Virtual start address of the back region |
| 8 | Root record virtual address |
| 12 | Unresolved allocator/tail value |

Native allocation uses a 96 MiB address space. A record pointer refers to a virtual address, not necessarily its compact file offset. Front addresses map directly; back addresses map to `BufferFrontSize + pointer - virtualBackStart`. `-1` is the linked-list sentinel. The converter indexes both physical regions and rejects pointers that do not refer to indexed record boundaries.

Every record begins:

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | uint16 | Record size in 8-byte units |
| 2 | uint8 | Payload offset in 4-byte units |
| 3 | uint8 | Record type |

Timestamped track records additionally have int32 next at +4, int32 previous at +8, float32 seconds at +12. Many event records have int32 target object ID at +16, with payload at +20. Always use each record's own payload offset.

## Active object table: critical pitfall

The root record is type 2. Its payload contains 2048 signed int32 hash-bucket pointers (8192 bytes). Walk each bucket's type 3 object chain using +4 as the next pointer. **Do not scan all type 3 records and assume they are active.** The compacted back region can retain stale object headers from an earlier recording. Native enumeration follows the root table, and the converter does the same. Root +4 is not a reliable count of active objects.

Each active type 3 object occupies 80 bytes:

| Offset | Type | Meaning |
| --- | --- | --- |
| 4 | int32 | Next object in hash bucket |
| 8 | int32 | Unresolved |
| 12 | int32 | Object ID |
| 16 | int32[8] | Channel heads; -1 means absent |
| 48 | uint16 | Index into trailing StringList for recorded display label; 65535 means absent |
| 50 | uint16 | Flags; debrief selection tests `flags & 0x21`; player tests `flags & 4` |
| 52 | uint8 | Icon type enum |
| 53 | uint8 | Category code; code 24 is special-cased as wingman in native code |
| 54 | uint8[2] | Unresolved extra codes |
| 56 | float64[3] | Icon offset, retained in native **centimeters** |

The category code is **not** proven to be the exported `ELiveGameObjectUniqueType` enum. Do not map it using that unrelated enum. `enums.json` contains the recovered icon enum and subtype enum. Codes include Air=1, Naval=3, Ground=5, LandBattleShip=11, Drone1=18 and Drone2=19.

## Object channels

| Channel | Record types | Payload |
| --- | --- | --- |
| 0 | 232â€“233 | int32 parent ID, uint16 socket string index, uint16 unresolved |
| 1 | 234â€“237 | Three float64 translation components |
| 2 | 238â€“241 | Four float32 quaternion components x,y,z,w |
| 3 | 242â€“245 | Three float64 auxiliary/relative translation components |
| 4 | 246â€“249 | Four float32 auxiliary/relative quaternion components |
| 5 | 250â€“251 | Complex player/flight state; not interpreted or exported |
| 6 | Unresolved | No established interpretation |
| 7 | 252â€“253 | uint32 state mask at payload start; remaining bytes unresolved |

Translation is in Unreal centimeters; JSON converts track positions and event locations to meters. Raw Unreal X/Y are horizontal and Z is up. No latitude/longitude, north orientation or geographic origin has been recovered. Parent/socket composition is not implemented. Retain parent and auxiliary tracks for future reconstruction; treating every track as an independent world-space marker may misplace attached objects.

Position samples occur around 5 Hz for the players in the four exported samples. Do not assume a fixed rate for all tracks. Timestamps are float32 seconds and may repeat at checkpoints or phase transitions. At equal timestamps the reference sampler keeps the last linked record. Normal record types 234/238/242/246 are treated as interpolation eligible; the remaining variants are conservatively exported as discontinuities. Exact variant semantics and native interpolation are unresolved.

## State and events: confidence limits

The exported state is always a raw uint32 mask. In sampled recordings:

| Bit | Correlated interpretation |
| --- | --- |
| 0 | Existence; falling edge correlates with removal |
| 1 | Alive; falling edge correlates with destruction |
| 2 | Target designation |
| 6 | Enemy affiliation |
| 7 | Allied affiliation |

Other bits remain unresolved. These are observations, not an exact native enum. Reference coloring uses this approximation. Record type 24 carries a float resembling health. Type 25 correlates with destruction, and type 29 carries a three-float64 location nearby in time. Across the four exported samples, all 119 falling-alive-bit events match type 25 and a nearby type 29 location. Exported destruction events are marked `confidence: correlated`; nearby location matching uses a 0.25-second window. No attacker, weapon or kill-credit association is established.

The converter includes raw payload hex for selected-unit event records below 232 with an event-style header, excluding structural types 2â€“5 and high-volume type 149 player controls. It does not export every buffer byte or every channel. Original saves should remain the source of truth for further reverse engineering.

## JSON interface, schema version 1

Root: `schema="ac8-tactical-replay"`, `schemaVersion=1`, `source` (filename, SHA-256, savedVersion), `mission`, `duration` in seconds, `coordinates`, `units`, `events`, `healthEvents`, `rawUnitEvents`, `validation`, `warnings`.

Each unit retains id, classIndex (legacy name for the label string index), flags, iconTypeCode, categoryCode, extraCodes and iconOffset, and adds labelStringIndex, recordedLabel, iconType, isPlayer, isWingman, startTime and tracks. Sample annotations may additionally provide displayName and nameSource; these are kept separate from the recorded label. **iconOffset alone retains centimeters**; position and relativePosition tracks and event positions are meters. Track rows:

```text
position / relativePosition:     [seconds, x, y, z, stepIntoSample]
quaternion / relativeQuaternion: [seconds, x, y, z, w, stepIntoSample]
parent:                         [seconds, parentId, socketStringIndex, unknown16]
state:                          [seconds, rawBitMask]
```

`stepIntoSample=1` means hold the previous pose until this sample's timestamp, then jump. Before/after track bounds the supplied sampler clamps to endpoints; use state/lifetime logic to determine visibility. Linear translation and normalized shortest-arc SLERP are provided as practical reference behavior. They are not proven identical to the native decoder.

Events contain time `t`, unitId, type (`destroyed` or `removed`), source and confidence; destruction may include position and recordTime. Raw events contain t, unitId, recordType and payloadHex. Health events include a correlated scalar value. Array samples preserve native precision in JSON number form; large coordinate offsets may benefit from a local rendering origin.

## Native evidence anchors

For the inspected executable, preferred image base is `0x140000000`. Static addresses are build-specific and some entry points jump to relocated bodies:

| Address | Observed function/behavior |
| --- | --- |
| 0x147836d80 | Replay buffer initialization, 96 MiB capacity |
| 0x147836e60 | Forward record allocation and packed record header |
| 0x1478374f0 | Root record and 2048-bucket table initialization |
| 0x147838a10 | Active object-table enumeration and debrief flag selection |
| 0x14782e290 | Debriefing initialization calling enumeration |
| 0x147831390 | Debriefing unit initialization |
| 0x147833720 | Unit role selection; player flag and wingman category special case |
| 0x147848080 | Unit registration |
| 0x146df78a0 â†’ 0x158daf5c0 | Debrief decoder constructor; speed defaults 1, 3, 6, subject to asset settings |

Relevant asset paths include `/Game/Maps/Menu/Briefing/PL_Debriefing`, `/Game/Blueprints/BriefingDebriefing/Debriefing/BP_DebriefingIcon`, `BP_DebriefingKillMarkManager`, `DA_BriefingDebriefingSettings`, and `/Game/BriefingDebriefing/Common/Icon/Niagara/NS_DebriefingRibbon`. Native classes include `ALiveDebriefingDecoder` and `ALiveDebriefingUnitActor`.

## Remaining work for faithful reproduction

Resolve absolute versus relative transform selection, parent socket transforms and icon offsets; recover exact checkpoint/teleport variant behavior and native interpolation; establish the full state mask and scripted visibility; recover dynamic label updates and remaining hash identities; align mission map geometry; recover exact icon scaling, trail fade and camera behavior; validate event semantics and kill credit across more missions and gameplay modes. The current toolkit supports an approximate telemetry viewer now, with these gaps explicit.

Label lookup was corroborated in six exported saves. Mission 29 examples: index 36 TU-95, 37 MIG-29A, 38 MIRAGE 2000-5, 39 Noise, 40 TASHA, 238 TU-160, 468 B-1, 573 LITTLE BEE. Labels are recorded strings, not proof of a particular 3D mesh, and do not establish radar lock.


## Name-source findings (2026-11-18)

- The StringList is a mixed pool of recorded strings, not only display labels: map/IGC paths (`Mission 028`, `/Game/Maps/...`), weapon blueprints, actor names (`WingmanObj_00_Coster_0`, `WingmanUnit_00_Kate_0`, `WingmanObj_00_Tasha_0`, `AObj01_Air_0_av8b_1`, `EObj01_W1_Bomber_6_tu95_0`), voice/event IDs (`Wingman_Coster_Hit_Enemy`, `LIVE_Harrier_A/E/I`, `Harrier_I_Enemy_Lockon_Me`) and faction/squad tags (`Ally_Brand`, `Ally_Shark`, `Ally_Shilage`). Display labels (TU-95, Noise, TASHA, LITTLE BEE, SHADOW 22/ARES) are plain English literals in this pool, not localization keys, so they are not looked up from a game string table at replay time.
- `NamedHashToIDMap` is a uint32 name-hash to replay object ID map (2855 entries in Mission 29; values include 21, 24, 27, 30, 801, 804, 2341). It very likely links actor names to objects (for example Coster, Tasha and the AV-8B actors). The hash function is not yet identified: CRC32, FNV, UE StrCrc32/Strihash/MemCrc32 and an attempted CityHash32 on the StringList did not match. It needs the native FName/FString hash routine from the executable.
- `Wingman_Coster_*` and `WingmanObj_00_Coster_0` independently confirm that a wingman named Coster exists in Mission 29. `Harrier_I`, `LIVE_Harrier_A/E/I` suggest Harrier voices A, E, I, which map onto Jackpot 1, 5, 9 (letter positions 1, 5, 9). This is circumstantial until the hash map assigns objects to actor names.
- State bit 4 (value 16) appears only in mask 91 (enemy bit plus bit 4), seen on F-4E at about 134 s and the four F-15Cs spawning at 264 s, which later become mask 139 (allied) at 324 s. The viewer treats bit 4 as unidentified (yellow); this is a correlation.

## Projectile tracks and kill attribution (2026-11-18)

- `objects()` returns every active record: Mission 29 has 17,978, but only 883 are debrief icon objects (flags `& 0x21`). Another 17,073 objects have `flags == 2`, no label, no state channel (7) and translation channels 1/3 with quaternions. They are **projectiles**: about 15,000 live roughly 1.5 s at roughly 1,100 m/s (gun rounds) and about 2,000 live 20-30 s (missiles). They are not exported by default.
- A projectile's first sample is within about 5 m of its shooter at launch time. Of 342 destroyed vehicles in Mission 29, 327 had a projectile within 200 m at the destruction time; 325 events were attributed by `attribute_kills.py` (missiles 319, guns 6). The result is stored as `events[].attacker` with `confidence` `inferred-high` (miss under 50 m) or `inferred-low`.
- This is a geometric inference, not a native kill-credit field. No explicit owner reference was found on the projectile records; channel 6 (present on about 2,000 projectiles) is still unresolved and is the best lead for a true owner/target link. Overlapping missiles, friendly fire and kills by wreckage/collision can be misattributed.
- Re-run after any re-export: `python attribute_kills.py PATH\Replay3.sav Replay3.json`, then rebuild the viewer. Re-exporting also loses display names (see `label-evidence.json`).
- Projectile objects linger at the impact point for several seconds after arriving, so a projectile being present at the moment of death is not proof of the killing blow. attacker.impactTime / secondsImpactToDeath record when the projectile first reached the victim; a gap above 2 s downgrades the event to inferred-low. In Mission 26 the CRUISER (object 18155) was hit by an AEGIS 17849 missile at 81.6 s (health event 131 to 127 at the same instant) but only destroyed at 87.9 s, 6.3 s later; it is the only such outlier among 67 missile/gun attributions there.

- The player's own gun rounds are not recorded as projectile objects: Mission 28 has about 15,000 gun-round objects, launched by AI aircraft (F-15C, F-16C, F-4E, NOISE, JACKPOT 9 and others) but essentially none by REX, and Mission 2 has only 80 rounds, all from an enemy MIG-21BIS. For a gun-only player the projectile method therefore finds nothing. attribute_kills.py adds a fallback (confidence inferred-aim): an unattributed kill with the player within 1.5 km and within 10 degrees of the player's heading is credited to the player's guns. All 10 Mission 2 kills (two recordings) fit within 1.5 km and 5 degrees, matching the user's guns-only play; in Mission 28 it picks up 2 kills at 4-5 degrees.

- Mission naming used by the user: user mission number = recorded MissionID minus 1 (MissionID 2 = M1 = Replay12/14, MissionID 3 = M2 = Replay13/15, MissionID 27 = M26 = Replay2, MissionID 29 = M28 = Replay3). StringList[0] and MapPath use a third numbering (e.g. Mission 002 for M1), so always go by MissionID.

## Sections (scene cuts)

Derived, not a native field. `detectSections` in `playback.mjs` finds times where the player's position jumps more than 2 km between two samples less than 1 s apart (scene transitions: the player and wingmen teleport, scene-specific units spawn and the rest end). Mission ID 30 (user M29) has cuts at 458.9 s and 465.3 s. `doc.sections` (array of start times in seconds) overrides detection if present. The viewer draws ticks on the timeline, has previous/next-section buttons, breaks trails at cuts and resets the dynamic camera.

## Player trigger (record type 68)

The player object carries type 68 records with a 4-byte payload: a first byte of 1 is a press and a first byte of 0 is a release (the other three bytes are a marker that differs per recording; a bare `00000000` also appears at release). In Missions 1, 2 and 4 the press and release counts match and the bursts line up with the player's gun kills, so `attribute_kills.py` reads them as the trigger and stores `playerFire.intervals` in the JSON. Missions 23 and 28 do not follow the pattern (one repeated value), so no trigger data is used there. This is an observation, not a documented field. Type 149 on the player is the flight-control stream (axes 25-31); it has no trigger channel.

## Projectile channel 6 (2026-11-19): not an owner/target link

Probed on Mission ID 29 (Replay3, 309 attributed missile kills) and Mission ID 30 (Replay11). Channel 6 exists only on projectiles that live long enough to be missiles (about 1,990 of 17,073 in Replay3), as 2 to 4 records of type 252, each 24 bytes: header, next (+4), prev (+8), float32 time (+12) and one uint32 at +16 (+20 is always 0).

- The uint32 splits as kind (low byte: 0, 1 or 2), category (second byte, about 30 distinct values) and a 16-bit upper value. Whole-word and shifted comparisons against `NamedHashToIDMap` keys and object header +8 found no matches; the map's values are 0..N-1 indexes, not object IDs.
- Chains: (kind 2,1,1) = 784 projectiles, 4 attributed to a kill; (kind 0,1,1) = 266, 223 attributed (84%); (1,1) = 840, 75 attributed. The last record is 20 s after the first, the missile lifetime. First-record kind 0 therefore marks a missile that hit a tracked vehicle, kind 2 one that did not (possibly guidance or lock state). This is a correlation.
- No tag identifies the victim (0 of 33 repeated kind-0 values map to one victim; no repeated tag maps to a single victim) and only about half of repeated final tags map to one shooter, so the value is not a shooter or victim hash. The 16-bit upper value repeats across unrelated shooters and victims. Meaning unresolved.

## Missiles and bombs fired (`fire` in the JSON)

Projectile objects carry no weapon type (every one has identical header fields) and no owner. `add_missiles.py` therefore infers, per unit: the shooter is the unit nearest the projectile's first sample (within 60 m); a projectile that accelerates is a missile. Gun rounds (constant speed) are deliberately **not counted**: there are thousands, the counts are unreliable, and the player's own gun rounds are recorded in some missions (Mission 4) but not in others (Missions 1 and 2). A **bomb** is a projectile that releases children: projectiles that start away from every unit but within 60 m of another projectile in flight (or one that ended up to 0.3 s earlier) are its submunitions, and a parent with two or more of them counts as one bomb (SOD in Mission 4 releases 3 to 5 each). Submunitions are not counted as separate missiles. Bombs cannot be told from missiles by their flight path (the SOD parent is powered), and a plain bomb with no children would be counted as a missile. `fire[unitId] = {m: [missile launch times], b: [[bomb time, children], ...]}`. The player's missiles and bombs are recorded (Mission 23).

## Moon 11 railgun, UAV APS shield and laser (observations, 2026-11; INCONCLUSIVE)

Observed in M29 and M26 only. These are patterns in the data, not decoded fields, and the sample sizes are small. Nothing in the export or the viewer uses them.

- **Railgun (Moon 11).** Her projectiles include slugs at 7,300-11,900 m/s that fly 2.0-2.75 s and are sampled only 2-4 times, always in salvos of three about 0.3 s apart. Two speed families recur: about 11.3-11.9 km/s and about 7.3-8.1 km/s (M29: 2:31.0, 3:52.2, 5:35.1, 5:52.6; M26: 12:19.1, 12:22.1, 12:39.7, plus two at 9:54). In M26 she is the aircraft labelled `Unknown` (the game has not identified her yet); the same triples and speeds make the match likely, not certain. Her other projectiles are NPC missiles that cap at 833 m/s but can fly up to 13.5 s.
- **UAVs** (`ESCORT UAV` in M29, `UNKNOWN UAV` in M26) have no projectiles and no fire records, only the usual health/destroy records. Their state mask toggles between 67 and 75, i.e. bit 3 (value 8), which is otherwise unexplained.
- **Possible APS shield.** Missiles that end 25-60 m from a UAV, a consistent radius of about 50 m: M29 41 cases (38 with UAV bit 3 clear), M26 12 cases (8 clear). The first M29 case is at 0:26.1, three wingman missiles within 0.2 s.
- **Possible laser takedown.** Missiles that end mid-air before 7 s, at least 150 m from any unit and within 2 km of a UAV: M29 11 cases (8 with bit 3 set, e.g. four missiles ending together at 2:06.2-2:06.4), M26 7 cases (7 with bit 3 set).
- **Possible meaning of bit 3:** clear = shield up, set = laser active. Supported by both missions but not proven; the M26 shield cases are only 8 of 12.
- **Type 120** records (32 bytes, 20-30 per second) exist only on Moon's child unit (M29 id 20681, 0:00-0:22) and on the X-40 nose unit's `LASER DESIGNATOR` child (M29 id 22105, from about 7:39). The payload contains a constant triple (-10.26, -9.63, 5.65) and varying fields that are not decoded; the link to lasers is a guess.
- **Not found:** any record that names a missile's fate (shot down by APS or laser); the fate is inferred only from where and when the missile ends.
### Projectile channel 6, follow-up tests (2026-11; negative results)

Checked against projectiles with a known shooter, victim and (for the player) weapon, in M26, M28, M29 and M30. Channel 6 holds records `(kind byte, category byte, 16-bit value)` with kind 0, 1 or 2.

- **Presence:** missiles and bombs have channel 6; gun rounds (990 wingman rounds in M29) and railgun slugs (12) have none. This separates guided from unguided projectiles and nothing finer.
- **Kind 2 (first record on most missiles):** the same `(category, value)` for every shooter in a mission, whatever the weapon: M29 `(2,144)` for the player's MSL and HCAA, Moon's missiles and the wingmen's; M28 `(2,33)`; M26 `(2,39)`; M30 `(2,135)` for MSL and XSDB alike. It is not a shooter ID or a weapon ID.
- **Kind 1 (repeated about 20 s apart):** not a victim ID or victim type. M30 has 27 distinct values over 97 kills, M28 153 over 307, M26 38 over 78; one value maps to several victim labels (for example `(192,14440)` is SLCM, MSL DISPENSER, MARKER UAV and unlabelled targets) and every label has many values.
- **Kind 0:** almost unique per victim (M30 64 distinct values for 64 victims); possibly an instance hash, not decoded.
- **Other per-projectile records:** type 37 (4 bytes at spawn, often 0.0 or a time a few seconds before launch), type 38 (impact position as 3 doubles in cm plus vectors and a counter) and type 39 (4 bytes) do not hold the shooter, victim or weapon either.

Conclusion so far: nothing on a projectile names its model. The weapon of a player launch comes from the weapon-cycle presses (types 71/69); for NPC projectiles only the flight (speed, acceleration, lifetime) and the shooter type tell them apart.