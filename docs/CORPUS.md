# Retained game profiles and winning routes

All **57 retained ROMs** have an exact-image story profile and a recorded winning
route: 17 V3, one V4, 33 V5, and six V8 builds. All 56 games other than LGOP have
a measured fixed maximum score. LGOP has player and counter metadata and a
complete winning route, but its randomized scoring has no fixed maximum.

Profiles supply player identity, score/move conventions and measured outcome
markers. Story identity uses the addressable image's SHA-256, not its filename.
The loading archive records each original file's hash, release, serial and header.
A different release needs its own measurements.

Each story link below opens its vector archive. The `walkthrough.json` member
contains the commands, input boundaries and expected measurements; it is read
in memory with Python's `zipfile`. These archives contain no ROM bytes, game
prose, memory dumps or save files. Route lengths count inputs after the recorded
opening, including character acknowledgements and menu answers. A win need not
attain the maximum score: both values are recorded separately.

| Story / vectors | Version | Release / serial | Player object | Maximum score | Seed | Route inputs | Final score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`ballyhoo.z3`](../tests/vectors/ballyhoo_vectors.zip) | 3 | 97 / 851218 | 211 | 200 | 0 | 416 | 200 |
| [`cutthroat.z3`](../tests/vectors/cutthroat_vectors.zip) | 3 | 23 / 840809 | 184 | 250 | 10 | 336 | 250 |
| [`enchanter.z3`](../tests/vectors/enchanter_vectors.zip) | 3 | 24 / 851118 | 55 | 400 | 0 | 265 | 400 |
| [`hhgg.z3`](../tests/vectors/hhgg_vectors.zip) | 3 | 59 / 851108 | 31 | 400 | 4 | 361 | 400 |
| [`hollywood.z3`](../tests/vectors/hollywood_vectors.zip) | 3 | 235 / 861118 | 50 | 150 | 0 | 397 | 150 |
| [`infidel.z3`](../tests/vectors/infidel_vectors.zip) | 3 | 22 / 830916 | 223 | 400 | 0 | 250 | 400 |
| [`lgop.z3`](../tests/vectors/lgop_vectors.zip) | 3 | 160 / 860521 | 199 | Variable | 42 | 389 | 326 |
| [`lurking.z3`](../tests/vectors/lurking_vectors.zip) | 3 | 219 / 870912 | 56 | 100 | 0 | 294 | 100 |
| [`planetfall.z3`](../tests/vectors/planetfall_vectors.zip) | 3 | 29 / 840118 | 236 | 80 | 0 | 399 | 80 |
| [`plundered.z3`](../tests/vectors/plundered_vectors.zip) | 3 | 26 / 870730 | 192 | 25 | 0 | 189 | 25 |
| [`seastalker.z3`](../tests/vectors/seastalker_vectors.zip) | 3 | 86 / 840320 | 191 | 100 | 0 | 204 | 100 |
| [`sorcerer.z3`](../tests/vectors/sorcerer_vectors.zip) | 3 | 18 / 860904 | 223 | 400 | 0 | 254 | 400 |
| [`spellbrkr.z3`](../tests/vectors/spellbrkr_vectors.zip) | 3 | 63 / 850916 | 52 | 600 | 0 | 412 | 600 |
| [`wishbringer.z3`](../tests/vectors/wishbringer_vectors.zip) | 3 | 68 / 850501 | 238 | 100 | 0 | 184 | 100 |
| [`zork1.z5`](../tests/vectors/zork1_vectors.zip) | 3 | 88 / 840726 | 4 | 350 | 12 | 396 | 350 |
| [`zork2.z5`](../tests/vectors/zork2_vectors.zip) | 3 | 48 / 840904 | 4 | 400 | 0 | 296 | 400 |
| [`zork3.z5`](../tests/vectors/zork3_vectors.zip) | 3 | 17 / 840727 | 202 | 7 | 0 | 273 | 7 |
| [`trinity.z4`](../tests/vectors/trinity_vectors.zip) | 4 | 12 / 860926 | 103 | 100 | 0 | 610 | 100 |
| [`905.z5`](../tests/vectors/905_vectors.zip) | 5 | 1 / 120724 | 28 | 1 | 42 | 22 | 1 |
| [`acorncourt.z5`](../tests/vectors/acorncourt_vectors.zip) | 5 | 3 / 970904 | 20 | 30 | 4 | 17 | 30 |
| [`advent.z5`](../tests/vectors/advent_vectors.zip) | 5 | 9 / 060321 | 20 | 350 | 5 | 277 | 350 |
| [`adventureland.z5`](../tests/vectors/adventureland_vectors.zip) | 5 | 1 / 961111 | 20 | 100 | 4 | 170 | 100 |
| [`awaken.z5`](../tests/vectors/awaken_vectors.zip) | 5 | 1 / 980726 | 20 | 50 | 0 | 57 | 50 |
| [`balances.z5`](../tests/vectors/balances_vectors.zip) | 5 | 5 / 961216 | 20 | 51 | 0 | 122 | 50 |
| [`curses.z5`](../tests/vectors/curses_vectors.zip) | 5 | 16 / 951024 | 15 | 550 | 0 | 816 | 450 |
| [`deephome.z5`](../tests/vectors/deephome_vectors.zip) | 5 | 1 / 991210 | 20 | 300 | 0 | 327 | 300 |
| [`detective.z5`](../tests/vectors/detective_vectors.zip) | 5 | 1 / 000715 | 90 | 360 | 0 | 51 | 360 |
| [`dragon.z5`](../tests/vectors/dragon_vectors.zip) | 5 | 2 / 040211 | 20 | 25 | 0 | 101 | 25 |
| [`enter.z5`](../tests/vectors/enter_vectors.zip) | 5 | 1 / 020428 | 20 | 20 | 0 | 102 | 20 |
| [`gold.z5`](../tests/vectors/gold_vectors.zip) | 5 | 1 / 090410 | 85 | 100 | 0 | 345 | 100 |
| [`huntdark.z5`](../tests/vectors/huntdark_vectors.zip) | 5 | 3 / 990918 | 17 | 1 | 0 | 67 | 1 |
| [`inhumane.z5`](../tests/vectors/inhumane_vectors.zip) | 5 | 2 / 950817 | 15 | 90 | 0 | 122 | 90 |
| [`jewel.z5`](../tests/vectors/jewel_vectors.zip) | 5 | 2 / 990710 | 211 | 90 | 0 | 223 | 90 |
| [`karn.z5`](../tests/vectors/karn_vectors.zip) | 5 | 2 / 961207 | 20 | 170 | 0 | 362 | 170 |
| [`library.z5`](../tests/vectors/library_vectors.zip) | 5 | 2 / 951204 | 15 | 30 | 0 | 52 | 30 |
| [`loose.z5`](../tests/vectors/loose_vectors.zip) | 5 | 2 / 981128 | 34 | 50 | 0 | 50 | 50 |
| [`ludicorp.z5`](../tests/vectors/ludicorp_vectors.zip) | 5 | 12 / 031010 | 20 | 150 | 0 | 364 | 150 |
| [`moonlit.z5`](../tests/vectors/moonlit_vectors.zip) | 5 | 1 / 020927 | 20 | 1 | 0 | 59 | 1 |
| [`murdac.z5`](../tests/vectors/murdac_vectors.zip) | 5 | 1 / 111115 | 7 | 250 | 0 | 304 | 249 |
| [`night.z5`](../tests/vectors/night_vectors.zip) | 5 | 1 / 961118 | 15 | 10 | 0 | 90 | 10 |
| [`omniquest.z5`](../tests/vectors/omniquest_vectors.zip) | 5 | 2 / 040127 | 20 | 50 | 0 | 78 | 50 |
| [`pentari.z5`](../tests/vectors/pentari_vectors.zip) | 5 | 6 / 030206 | 20 | 70 | 0 | 49 | 70 |
| [`reverb.z5`](../tests/vectors/reverb_vectors.zip) | 5 | 1 / 990110 | 20 | 50 | 0 | 74 | 50 |
| [`sherlock.z5`](../tests/vectors/sherlock_vectors.zip) | 5 | 21 / 871214 | 232 | 100 | 0 | 339 | 100 |
| [`spirit.z5`](../tests/vectors/spirit_vectors.zip) | 5 | 3 / 960606 | 15 | 250 | 0 | 1264 | 250 |
| [`temple.z5`](../tests/vectors/temple_vectors.zip) | 5 | 2 / 021118 | 89 | 35 | 0 | 181 | 35 |
| [`theatre.z5`](../tests/vectors/theatre_vectors.zip) | 5 | 2 / 951203 | 15 | 50 | 0 | 296 | 47 |
| [`tryst205.z5`](../tests/vectors/tryst205_vectors.zip) | 5 | 205 / 970629 | 20 | 350 | 0 | 518 | 350 |
| [`weapon.z5`](../tests/vectors/weapon_vectors.zip) | 5 | 1 / 010706 | 20 | 1 | 0 | 72 | 1 |
| [`zenon.z5`](../tests/vectors/zenon_vectors.zip) | 5 | 2 / 100122 | 20 | 20 | 0 | 83 | 20 |
| [`ztuu.z5`](../tests/vectors/ztuu_vectors.zip) | 5 | 16 / 970828 | 20 | 100 | 0 | 84 | 100 |
| [`afflicted.z8`](../tests/vectors/afflicted_vectors.zip) | 8 | 1 / 080906 | 57 | 75 | 42 | 98 | 75 |
| [`anchor.z8`](../tests/vectors/anchor_vectors.zip) | 8 | 5 / 990206 | 20 | 100 | 42 | 531 | 99 |
| [`lostpig.z8`](../tests/vectors/lostpig_vectors.zip) | 8 | 2 / 080406 | 87 | 7 | 42 | 146 | 6 |
| [`partyfoul.z8`](../tests/vectors/partyfoul_vectors.zip) | 8 | 4 / 100208 | 48 | 1 | 42 | 59 | 1 |
| [`snacktime.z8`](../tests/vectors/snacktime_vectors.zip) | 8 | 1 / 080929 | 44 | 50 | 42 | 34 | 50 |
| [`yomomma.z8`](../tests/vectors/yomomma_vectors.zip) | 8 | 3 / 100228 | 59 | 35 | 42 | 98 | 34 |

The fast suite checks every row's profile, fixed maximum (except LGOP), player
identity where recorded, route hash, seed and final recorded victory. This
prevents another story from silently losing metadata or complete-route coverage.
The manual comprehensive suite executes the routes against live public-reference
behavior on Linux and replays their hash vectors on the portable matrix.

See [V3](V3_GAMES.md), [V4](V4.md), [V5](V5.md), [V8](V8.md), and
[LGOP](LGOP.md) for exact behavioral differences and coverage. In particular,
Anchorhead's seed-42 route repairs its randomized safe/flute answers, and Party
Foul's route repairs NPC timing. Those command lists are in `tests/routes/`;
other V8 routes are obtained from Jericho's documented `get_walkthrough()` API.
