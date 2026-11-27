# Site Specification: The site around every page

**Status**: Baseline -- describes the site as it works today
**Verified against**: `main` on 2026-10-21; the profile in the folded menu against branch
feat/menu-my-account on 2026-11-21, its place before Search against feat/menu-cabinet-before-search,
the profile in a desktop's row against branch menu-cabinet-desktop-deploy-schedule on 2026-11-22, the virtual
ride's settings with the account, remembered devices, setup layout and ride invitation against branch
virtual-ride-tweaks on 2026-11-24, the setup on a 320 px phone (Safari's menus, the route cards) against branch
fix/trainer-webkit-narrow-setup on 2026-11-24, the routes on their streets and the full screen against branch
fix/trainer-routes-on-streets on 2026-11-25
**Code**: `cycling_site/` (templates `base.html`, `_setup_hint.html`, `_share_button.html`;
`setup_hints.py`, `context_processors.py`, `middleware.py`, `richtext.py`, `storage.py`), `home/` (home page, site
content, legal pages), `search/`
**Tests**: `home/tests.py`, `tests/test_home_cards.py`, `cycling_site/tests.py`, `tests/test_setup_hints.py`,
`tests/test_share_button.py`, `tests/test_language_switch.py`, `tests/test_locale_cache.py`,
`tests/test_kazakh_account_pages.py`, `tests/test_page_meta.py`, `tests/test_favicon.py`, `search/tests.py`,
`tests/test_template_comments.py`, `tests/test_sign_in_link.py`, `tests/test_signing_out.py`,
`tests/test_menu_profile_link.py`,
`tests/e2e/test_home_page.py`, `test_header.py`, `test_locale.py`, `test_setup_hints.py`,
`test_share_button.py`, `test_reader_timezone.py`, `test_sign_in_returns.py`, `test_sign_out_stays.py`,
`test_menu_profile.py`, `test_navbar_fits.py`
**Related**: [accounts](accounts.md), [skins](skins.md), [search visibility](search-visibility.md)

## Overview

Every page shares one frame: a sticky navbar (site title, News, Calendar, Map and About when their
pages exist, Ratings ([ratings](ratings.md), right after Calendar), Knowledge Base, Gallery ([gallery](gallery.md)), Virtual ride, Statistics for the owners
([statistics](statistics.md)), a member's profile -- in the folded menu on a phone and in the row on a
desktop -- Search last, the skin chooser, the three language buttons, sign-in or the member's
menu (the profile too, the admin for staff, sign-out); sign-in brings the reader back to the page it was pressed on, filters and all, except from an
account page, and signing out stays on the page -- or, where a guest may not open it, goes to the
home page in its language), a banner of moderation tasks for moderators, one of requests waiting for a member's answer, one of the events they took part in to rate and, for the owners while none is marked, one asking to mark the agents' account ([ratings](ratings.md))
([accounts](accounts.md)), one setup hint, the page, and a footer with the legal pages and a link to
report a bug. The menu's and the footer's links stay in the page's language: a Wagtail page (the
home page, Map, Knowledge Base) is addressed under its own language's prefix
(`cycling_site/page_mixins.OwnLanguageUrlMixin`), not under the default language's.

**Virtual ride** (`trainer/`, `/<lang>/virtual-ride/`) frames an indoor-trainer page,
`trainer/static/trainer/alatau.html`, in an iframe that may use Web Bluetooth, the screen wake
lock and full screen. "Open full screen" puts that frame on the whole screen, as a protocol's button does, and
Escape brings the page back; where a frame cannot go full screen (an iPhone) the link opens the same page on its
own (`trainer/static/trainer/virtual-ride.js`, `tests/e2e/test_virtual_ride.py`). The page is a static file that
loads its own files from `trainer/static/trainer/alatau/`, in the order it lists them: `alatau.css`, its
words (`text/<lang>.js`), its maps (`maps/`, below), its rider catalogue (`data/`) and its code, a file
per part of it (`js/`: the physics, the ride, the scene, the riders, the devices, the HUD, the site's API and the
rest). The ride is stepped apart from its drawing: the physics (`js/physics.js` -- the speed from
power or gear, the riders' drag, the bots, what a smart trainer is set to) and the ride's state and
step (`js/ride.js` -- the countdown, the rider, the bots, laps, sights, the finish, a plan's steps)
neither read the page nor draw, and nothing else steps the physics. Each frame the ride takes its
step, the trainer is told the grade -- scaled by the setup page's difficulty, which the page says the legs feel and
the speed never does: that comes from the route's own grade and the power -- and the rider's own drag (the
rolling resistance of their bike
and CdA x air density from their height, weight and bike, the numbers the ride moves them by, less
the share a wake ahead takes), and the scene and the HUD are drawn from the ride's state; what
happened in the step reaches the page through `rideHooks`. Without a power source -- a smart trainer or a power
meter -- the power comes from a wheel or cadence sensor by the trainer type the setup page names (fluid, magnetic,
rollers; a smart one counts as fluid), and the page says the type matters only then. The demo's power runs to
5 kW on a progressive slider, its steps finer near nothing than near the top. The air's density is the International
Standard Atmosphere's at the height of the road under each rider. A rider close behind another, the
rider and the bots alike, rides in the best wake ahead: the share of the air drag saved follows
on-site measurements of riders pedalling (Spoelstra et al. 2020: 45 % in line 0.7 m behind the
wheel, 1.3 points more for each 10 cm closer, 3.9 points less for each 10 cm aside), and the same
slopes further out, so it is gone 4.2 m back or 1.2-1.4 m aside, scaled by whom the rider hides behind -- the
square root of the drag areas ahead and behind, within 0.8 to 1.2: a model, the measurements saying only that a
bigger rider ahead shelters more (37 % behind a small rider on a TT bike, 53 % behind a big one on an MTB); a smart
trainer is told a change of that drag within the second. A cadence sensor alone rides by the physics, from the trainer's
power curve, unless the rider chose the gear's speed; a step of the own plan by gears rides at its
gear's speed whatever the choice.
A signed-in member's settings on the page -- body, bike, trainer, mode, plan -- are kept with their account
too, so every device they sign in on shows the same. The account stamps each copy by the site's clock,
never a device's: a browser's change, sent a moment and a half after it, replaces the account's copy
only if that is the copy the browser had, and otherwise the later copy comes to the browser. Settings a
browser never changed are never sent, so a fresh browser's defaults cannot replace what the member chose
elsewhere, and settings an old browser kept before the account did go only to an account still empty
(`tests/e2e/test_virtual_ride.py`). Bluetooth devices and the auto-connect box stay with the browser.
Every device once connected is remembered in the browser, by the id the browser gives it for the site
and its name, newest first, at most eight; one not connected now is listed with Connect and Forget.
Connect opens it again without the chooser where the browser lists the site's devices
(`navigator.bluetooth.getDevices`, in Chrome behind `chrome://flags/#enable-web-bluetooth-new-permissions-backend`),
and elsewhere opens the chooser with that device alone in it. With "Connect automatically" on, the
page opens every remembered device it may as it starts and tries each until it wakes; where the
browser does not allow it, the box says which flag turns it on; where devices it may open have not come in
within a few seconds -- a browser that has not searched since it started cannot reach them, Chrome on a Mac
among them -- the page says to press Connect a device and close the chooser once they connect: its search
finds them (`tests/e2e/test_virtual_ride.py`).
A smart trainer is sent one command at a time, each once it has answered the one
before, as FTMS requires; a trainer that never answers is given two seconds a command and driven all
the same. A trainer that no longer grants control is asked for it once more and, if it still says no,
is shown as not under control and left alone; a grade sent before the trainer reconnected is sent
again. A ride on a trainer that does not ride the route -- it gave no control, or it refuses the grade -- says
so under the grade in words, dark on amber, rather than only writing "gradient" where "trainer 2 %" would stand;
once a ride, after any message already on screen, a message says why. A refusal belongs to the connection that
made it, a trainer holding a workout's power is riding as asked, and a bike that only sends its data (no FTMS
control point) is not warned: its resistance is set by hand. A box on the setup page is ticked from its
box and its words, not from the empty row beside them. A trainer whose Fitness Machine Feature says it holds a
power (Power Target Setting) is set to
a workout step's power instead of the grade, within the range it reports, while the HUD's ERG switch
is on (FTMS Set Target Power); off, it goes back to the grade and the rider holds the power by feel.
Back on the setup page a trainer is set to a flat road, not left holding a power. The plan screen
offers the member's own plan by gears and cadence and, once they connected intervals.icu, the cycling
workouts planned there for today and the next seven days (issue #471). A picked workout is read in
watts through the site and ridden step by step: its target (a ramp moves from one power to the
other), the cadence it asks for, its cues as messages on the way, the time spent on the target; a
rider without a smart trainer sees the target beside their estimated power, and the demo rides it.
Only the picked workout's id is kept in the browser, and a workout that did not load holds the start
until it loads or another plan is picked (`tests/e2e/test_virtual_ride_workouts.py`). Under the plan screen
the plan to ride is drawn a bar a step, as long as the step and as high as its target: the power where the plan
sets one (a ramp a slope), else the cadence, each bar titled with its time and target. A frame's time is ridden in steps of at most 50 ms, so the ride keeps real time on a device
that draws two frames a second or more; a longer
pause, such as a hidden page, counts as half a second. Production names each file after a hash of
its content, as it names the page, and the page links those names (`cycling_site/storage.py`), so the
page and its files are cached together. The ride
runs in the browser: the page talks to the site only through `Site.req` (`js/site.js`), to
`/api/v1/virtual-ride/` -- who rides, a member's records and rides, the lobby and group races, a
finished ride and its Strava upload, the workouts planned in intervals.icu. The page is updated from delivered revisions. It speaks the language its address names (`?lang=ru|kk|en`, which the
site's page passes from its own; Russian without one): its texts, units, number and date formats
and the names of its routes, landmarks and riders come from the page itself -- its words in `text/`,
the names in `maps/` and `data/`, the formats from its language and locale (`LANG`, `LOCALE` in `js/page.js`) --
rather than from the translation catalogues: an exception to FR-SHL-006 that keeps the page standing on its own, apart
from the site's templates. A route name the page sends with a saved ride or a group race is in the
language the page spoke then; the page itself shows the routes it knows in its current language,
the profile shows the stored name. A member's page records the ride's track, a point a second: where
the rider is on the route's map (a route follows the streets its description names, along OpenStreetMap's
ways on the side a rider keeps to, each corner rounded within the street; its heights are SRTM's, smoothed over
150 m, and the page lays its points 4 m apart along it and averages their heights three times over 60 m, so the
grade rises and falls without steps, and bends it between them as their ways say, so a rider turns through a
corner smoothly; the map's sights stand where OpenStreetMap has them), height, distance, speed, power, cadence and pulse.
The setup page lays its sections one a row -- the route, the mode, riding with friends, the rider, the devices and
the bike, the ones set
once last -- with the lines on where the rides go under them all; a 320 px phone never scrolls it sideways,
whatever a remembered device is called or a menu has chosen, Safari included, and the route cards keep
inside their section. It offers a member who
has not connected Strava to connect it with Strava's button, and tells one who has that the rides go
there, with a link to the profile's Strava card to manage it (`tests/e2e/test_virtual_ride.py`);
the results say when the ride is on Strava ("View on Strava") or why not, with "Send again"; a ride
Strava already has is linked to that activity, never sent twice, and after half a minute of
processing the page says to look in Strava later. A ride sent to Strava or intervals.icu carries a
description: an invitation to ride with the club and the virtual ride page's address, both in the
rider's language -- their profile's choice, else the language of the page they rode on -- the club named by
`ORGANIZATION_SHORT_NAME`, else `ORGANIZATION_NAME`, else the site's name (`trainer/invitation.py`,
`tests/test_ride_invitation.py`). A
guest's progress stays in their
browser, as does an unconfirmed account's; for a confirmed member the page saves every finished ride through `/api/v1/virtual-ride/`
(see [the API](api.md)), and their records -- best time per route, peak power, top speed, totals --
are derived from those rides and shown on the profile ([accounts](accounts.md)); rides in demo mode
are kept but never count. The mode's box "Wind" sets a wind -- the bearing it blows from, one of
eight, and its speed, 1-30 m/s, the most a smart trainer can be told -- kept with the other settings (in the
browser, and with a member's account): the air drags each rider by their speed through it, the wind's share along
their way (the side wind is left out), a smart trainer is told the wind against the rider, the HUD says it is
ahead, behind or beside them, and the start's
summary names it. A ride with wind is saved with it and marked so; it counts for peak power, the rider's own, but
sets no route record or top speed. In a group race every member rides in its host's wind, kept with the race and
named on its card; the own wind is for riding alone (`tests/e2e/test_virtual_ride.py`,
`tests/test_virtual_ride_api.py`). Members ride together as the mode says: a free ride gathers a ride together
(everyone starting at once; no event, no time trial), a race a race with its settings at hand -- a group race or
an individual time trial, the gap between the categories' starts or the interval between the riders', whether
categories draft each other -- and a workout nothing: each rides their own plan, and block 3 says so and where to
go instead; a link to a ride or a race opened in a workout turns the page once to the mode that rides it. The
settings page lists who else is on it and the open rides and races, each card saying which; a member gathers one
on the chosen route with a start 20 s to 1 h away (the
page offers 30 s to 1 h) or at a date and time on their own clock, up to a year ahead; one host's races start an
hour apart at least, ten waiting at most (every lobby lists them all), and a member joins any race an hour from the
others they are in. Others join, and every
member's page starts it at the same server time; a page waits only for its member's race starting within the hour,
and a card further ahead names its day and time; on the card of a ride or race the member is in, the time to its
start counts down each second in days, hours, minutes and seconds. A time trial without an event starts its riders an interval
apart in the order they joined, its card naming each rider's own start, and the lobby lists it until moments after
its last rider's. At a date and time a box, "Add it to the calendar as an event" (as it was left last time, in the
browser), sends the gather button on: it gathers the ride or the race then (or takes the member's own of that kind on
that route at that minute) and sends the whole window to the event form filled from it
([events](events.md), story 1.6): a ride's words or a race's in ru, kk and en round the route's own way and finish
(each route of a map carries them, `event`), the type "Virtual Ride" and the discipline "Coffee Ride" for a ride,
"Road Race" or "Individual Time Trial" for a race by its mode; the route's start as its venue in the virtual world
-- "Virtual world: start of the route ...", so that nobody comes there to meet -- the one so named within 100 m of it,
else one proposed then under the nearest public city (public for an organizer, awaiting review for anyone else); the
ride or race itself, which the event's page opens as "Open the ride" and its forms show as its link, set by the site
and never typed (`Competition.virtual_ride`; `virtual_ride_url` in the API), the words "on the ride's page" linking to it
in the description; the route's track, attached as the event's track file when it is saved unless the member chose a
file of their own; the ride's picture for a chat's card, 1200 by 630 -- the route's view in the virtual world
(`maps/<map>/views/<route>.jpg`, rendered from its scene) under the logo of the skin `RIDE_PICTURE_SKIN` names, the
day and time, the title and the route's length and climb in the page's language, in that skin's type -- shown on the
form and attached as the event's link preview image unless the member chose one (`calendar_app/ride_picture.py`; a
route without a view, or a skin without a logo and fonts, has none); and for a race -- an organizer's only, as only an organizer's form registers riders --
registration on the site with the categories Men (bibs 100-999) and Women (1-99), born from 1900 on, three
laps each on a loop, each as many riders as its bibs and the race 999, a Strava link asked of each and listed, and the race itself, which
the event holds once saved. The form takes its draft's extras only with the key the draft gave it, so a draft left
over never lands on an event made by hand (`calendar_app/draft.py`, `tests/test_event_draft.py`). The page fills
the start's time with its UTC offset, its day, the link on the site's page in each language, the route's name,
length and climb, the wind and the word on the button that joins it, and for a race how it starts and, on a loop,
whose laps; the date goes into the event's date. "Start" while waiting rides alone and
leaves the race to the others: a host who leaves hands it to the
rider who joined next, and only a host alone in it cancels it that way ("Cancel" cancels it for all). Each
race card has "Share": the phone's share sheet, or the link copied, to `/<lang>/virtual-ride/?group=<id>`;
that address opens the trainer with the race marked on its card in words and colour and scrolled
into view, tells a guest to sign in and brings them back to it, and says when the race was cancelled,
has started or does not exist. During a group race, or a free ride
on the same route, each page reports its position about once a second and draws the others
(`trainer/live.py`; rows older than 15 s count as gone). Group results are the members' saved rides,
fastest first (a ride together names no winner); deleting one moves the others up. A race with protocols
(specs/495-virtual-race) is a race an event holds: made with its event from the trainer as above, or through the
API (`POST /api/v1/virtual-ride/groups` with `competition_id`) by the event's organizer or an admin for any public
event not over, with the mode, gaps, interval and drafting rule the race keeps. Only riders registered for the
event join it (a rider who is not
is sent to the event's page), each with a bib: the one the event gave their registration, else the first free one
in their category's range, kept across leaving and joining; the bib is drawn on every rider's back and named on
the race's card with the event, the rider's category, laps and own start. A rider rides their category's laps on a
loop, a route that is not one once; the control points are the start-finish line and the route's turns back, each
at its middle, where the way there and the way back come closest (`turnPoints`: Granfondo 2026's two, the smooth
one by Vostochka on Al-Farabi among them). The page reports each
crossing with its moment on the site's clock, the ones not taken yet with every call until one is answered --
from the menu too, so a rider gone back at once still sends their finish -- and the site writes the start list,
the categories' starts and the crossings into the event's timing streams as the device `virtual-race-<id>`, for
FinishProtocolGenerator's "Get data from site"; only while the event keeps its upload token, which never reaches a
rider's browser (`tests/test_virtual_race.py`, `tests/e2e/test_virtual_race.py`). On a phone (a coarse pointer)
the start's summary says a route with many buildings and streets (Granfondo 2026, the Medeu climb, the centre's
loop) may run slowly. The settings page is separate from the ride and offers racing, a workout and free riding. It
includes rider height/mass and bicycle type/mass; the rider wears the UBT kit, with third-person view as the
default. Free rides can be finished from the pause menu, and lap a loop only: on a route from one place to another a free
ride is over at its finish, saved as when its rider ends it (a workout rides its plan on from the start); a workout whose plan is done rides on as a free ride, the
trainer let go of its power, and nothing is saved or sent until the rider ends it there, the time after the plan in
it too. During a ride the HUD shows, in one row on top, the speed,
the distance, the metres climbed and the time over a bar of the route (or the plan, or the lap) done; under it the
power, large, with the heart rate (the zone's colour on its heart, the figure white) and the cadence, and the ride's
average power; in a cadence plan, from the countdown on, the step's target beside the power, the cadence coloured by
how far it is from it, the step's average cadence and the list of steps on the left; on the right the grade over the
minimap and under it the street ridden, named from OpenStreetMap in the page's language (a racetrack or a road
between two villages that no street runs along by the route's own name; nothing where the map names none) and,
when there are other riders, those nearby with the gaps in seconds; hints read as a large line over
the road. A phone held upright gets one column, a tablet keeps the blocks apart, and nothing animates for a reader
who asked for less motion (issue #434). Record labels keep the date and demo marker distinct. Tests:
`tests/test_virtual_ride.py`, `tests/test_virtual_ride_api.py`, `tests/test_static_storage.py`,
`tests/e2e/test_virtual_ride.py`.

**Maps.** A map is a city or a region, in a folder of its own: `maps/<id>/map.js`, one `addMap({...})` with the
map's data, in JSON, and nothing else (`js/maps.js`) -- its id, the folder's name; its name; its origin, a point
among its routes the scene is laid out from in metres east and south, so a map anywhere keeps its
distances and a rider's track its coordinates; its mountains, when it has a range rising to the south
(how far south of the origin its foot lies at the nearest; a map without them gets none) -- a route far from
its map's others, as a region's lie tens of kilometres apart, carries its own origin and mountains; its routes,
each a key, a name and a description, the points (latitude, longitude, height in metres), whether it
is a loop, the road's width and lanes (one lane, a racetrack's, has no centre line), the scenery drawn along it
(`city`, `gorge`, `steppe`, or `racetrack`: the steppe with no tree along its edges), its own buildings, barriers and
trees when it has them (footprints with a height; a guardrail and a catch fence a gap beyond each edge, broken at the
buildings; rows and woods, in the steppe or on a racetrack, instead of trees scattered at random -- all as
OpenStreetMap maps them) and the way and the finish
an event on it is written round (`event`); and the
sights along them, each the object it is built from, a name, a place and the room it takes -- a route
passes its own map's sights only. Every name is in ru, kk and en. The page lists each map's file, a
line each, in the order the menu shows the cities, so a new map is its folder and that line; a map
without routes is shown as coming soon. A map's button lists its routes and picks the first of them;
a first visit, or a remembered route no map has any more, starts on the first map's first route. A
route's key is its own across every map and stays as it is: the members' saved rides and group races
keep it. The objects the sights are built from are shared by every map, a file each in `objects/`,
named after the object it adds (`addObject('<type>', build)`, `js/landmarks.js`), and listed by the
page too; a new kind of sight is its object's file and that line.
A route may come back onto road it rode -- out to a turn and back along one road, round a loop of a turn: that
road is drawn once, each way in its own lane, and a route that ends where it starts finishes on its start's line,
under one arch for both; turned round at its start as at its far end, it is a loop ridden lap after lap
(Kyrbaltabay-Tuganbay; `scripts/virtual_ride/turn_at_start.py`). A map's relief -- SRTM heights on a grid round its routes -- draws the land beyond the
scenery's own ground as it is: the real ranges, hills and valleys, lowered by the Earth's curve as a rider sees
them, and not drawn over that ground; within 400 m of that ground's edge the ground comes to
the relief's own surface, on the triangles the relief is drawn as, so they meet there within a metre. A map without one raises a range instead, which runs 150 km either
way from the origin, so it never ends in view. A range or relief farther
than 9.5 km from the route's origin rises to its foot from the plain and
shows through a quarter of the haze beyond 9.5 km; a nearer one keeps the scene's haze. Trees, houses and sights
stand on the ground as drawn -- flat between the terrain's vertices -- and reach into it at its lowest under them,
their tops where they were; a sight that spreads over the land, a cable car or ski jumps, stands on each of its
pylons, stations and legs; one that lies flat on it, a rink, has the ground under it and round it laid at its
level -- Medeu's ice, its oval, stands and floodlights, in a bowl of the valley's floor; a dam lies on the land
it crosses, Medeu's along its crest as OpenStreetMap draws it, its stair climbing the face towards the route. The scenery's own ground lies a little under the road beside it and rises, from 80 m off
it over the next 500 m, to the land SRTM has there -- a city's slopes and hills, Kok-Tobe and the Sunkar hill on
finer grids of their own, each giving way to the map's grid over its outer three cells; a gorge's walls rise to it
from a few metres off its road, the Medeu gorge's on a grid a
thousandth of a degree fine over its whole scenery, and only a gorge on a map without a relief has its walls drawn.
Outside a tunnel's cutting the ground as drawn keeps 10 cm under the road and what lies beside it: where a plane of
it leaning on a wall would rise over them, its vertices go down as far. What a route carries from OpenStreetMap
stands round it: the
buildings with their heights and, where known, colours; the roads it meets and passes, on the ground and rising onto
its road where they meet it, under it where they cross; footbridges and road bridges over it, clear of its road on
piers beside it, the roads onto a road bridge climbing onto its deck up ramps between retaining walls; roads
under it down a cutting between walls; parapets along its own bridges; its tunnels, the road
down a ramp between walls under a roof the crossing street runs over, closed at each portal by its face and the
street's parapet, the land at the ground line up to the walls and
none inside them; power lines on towers or poles, their wires sagging high over the road, and railways and rivers,
as far as a rider sees them; canals and ponds; trees in rows, woods, parks and alone. Every route carries them, the
ones made before the tools too (`scripts/virtual_ride/`, the `virtual-ride-routes` skill). Between a dual
carriageway's two halves lies their median -- a pavement each way where it is wide, a concrete barrier down a
narrow one -- and one road ridden twice has one height, the barometer's lag up and down a slope evened out. Where
a route's points carry the rider's line, the rider rides it -- the source track's way through a corner it took by
the apex, the right lane elsewhere -- with the bunch round it and the camera on it, always on the road. A sight
shows on a route within its own reach, else 14 km for one seen from afar, else 1.3 km; a building OpenStreetMap
outlines may be one, drawn to its outline and height with its name lit on its roof (the Royal Tulip hotel by
Medeu's way). Tests:
`tests/test_virtual_ride_maps.py`, `tests/e2e/test_virtual_ride.py`, `tests/e2e/test_virtual_ride_surroundings.py`.

## User Scenarios

### Story 1 -- Read in my language (P1)

1. **Given** a visitor opens the bare address, **Then** they are redirected to the language their
   browser asks for (Russian by default), and that redirect is never cached.
2. **Given** a reader presses a language button (RU, KK, EN), **Then** the same page opens in that
   language -- from a page in any language, whatever the reader chose before, as when a Russian link
   from a chat opens on an English phone -- and the choice holds across pages and when the bare
   address is opened again; a member's
   choice is written to their profile and outranks the cookie. Each button shows the language's code
   as its address writes it -- KK, not the country's KZ -- and names the language in that language,
   for a screen reader and as a pointer's hint (#388).
3. **Given** an address that names its language, **Then** it stays in that language.

### Story 2 -- The home page (P2)

1. **Given** the home page, **Then** it shows the owner's cards in their order, each a heading and a
   rich text per language (a language without its own words falls back as every data field does).
   Every skin draws them as tiles, as many to a row as fit and one to a row on a phone -- the site's
   own skins as cards in their colours, UBT Almaty and Dark UBT in their own style --, the first
   spanning the row when it has no heading or repeats the page's title.
2. **Given** the owner, **Then** they edit the site content -- the navbar title and the tab title per
   language -- in three language tabs, and below it add, change, move up or down and delete cards,
   each in a form of its own with three language tabs; a card with no heading and no text in any
   language is refused. Nobody else sees the edit button; on these pages a guest is sent to sign in
   and any other member gets a 403. The cards are the owner's through the API too
   (`/api/v1/home/cards/`, [API](api.md)).

### Story 3 -- Setup hints (P2, issue #319)

1. **Given** a signed-out reader, **Then** every page except the account pages (sign-in, sign-up,
   the "continue with a service" steps) and a missing page asks them to sign in and brings them back
   afterwards; it cannot be closed and is not quoted by search engines.
2. **Given** a member, **Then** one hint at a time names the next thing to set up, in this order: an
   unconfirmed e-mail first (cannot be closed), then calendar preferences (only on the calendar,
   list and map), then the data a race entry needs, then a second way to sign in, then Strava;
   nothing once everything is set; members get none on the account pages (profile, sign-in methods
   and the like) or on the race entry form, which says itself what is missing.
3. **Given** a member turns a hint off (after confirming), **Then** the next one appears; an unknown
   hint is not stored and a foreign return address is not followed.

### Story 4 -- Share a page (P3, issue #327)

1. **Given** a public page -- the calendar, list and map (with their filters), news, a news article,
   search, the legal pages, a public event's participant list -- **Then** a share button beside the
   heading hands the address to the system share sheet, or copies it and says so.
2. **Given** an event page, **Then** a public event shares its address; an invite-only one shares its
   invitation link, and only with the people who may edit it; invitees, hidden events and events
   awaiting review get no button; personal pages have none.

### Story 5 -- Search (P3)

1. **Given** a query, **Then** it finds published pages in the reader's language, approved events,
   news, knowledge articles written in the reader's language, and locations; hidden and deleted ones
   are not found, nor a place awaiting review but by its proposer and its moderators (FR-LOC-003);
   a bad or out-of-range page number does not fail.

### Edge Cases

- Times are shown in the reader's zone, and the server's "today" is theirs: the page's script keeps
  the browser's zone in a `tz` cookie and `ReaderTimezoneMiddleware` activates it. Until the
  browser has reported one (the first page, a crawler, a feed reader), or when the cookie is not a
  zone, the site's `TIME_ZONE` setting is used (issue #344).
- A missing page answers 404 with the site's template in every language, offering a link home that
  names a language; an address without a language is sent to one first.
- Django request errors and Gunicorn errors (including worker timeouts after application
  initialization, with `--preload` on the host) are mailed to the admins when not in debug.
  Warnings and expected HTTP 503 availability responses are logged without email; an actual
  exception attached to a 503 still notifies admins. This keeps storage retries from flooding
  the mailbox or occupying the web threads with SMTP. SMTP operations have a five-second timeout by default
  (`EMAIL_TIMEOUT`), so reporting an error cannot wait indefinitely. An unavailable server or
  a proxy-generated 502 without an application/server log still needs external monitoring.
  Media is served in production and a missing file is a 404.
- Every page declares a canonical address, a title without stray whitespace, a translated fallback
  description and a social image with its size; an event page's title and description name the
  event, its date and place.

## Functional Requirements

- **FR-SHL-001**: Three languages (ru default, kk, en); the language buttons read RU, KK, EN (#388).
  A string a package ships no Kazakh for -- django-allauth's pages and mails, Django's password
  rules, form errors and CSRF refusal -- would fall back to Russian, the default language; its
  Kazakh is kept in `cycling_site/locale_third_party/`, with the Russian of a Django string its own
  Russian lacks (`tests/test_kazakh_account_pages.py`,
  `registrations/tests.py::FormLabelsInThePageLanguageTests`).
- **FR-SHL-002**: The privacy policy and the terms of use live at stable addresses, are public and
  translated, linked from every footer; the privacy policy states what Strava data is used, that a
  member's settings on the virtual ride page -- height, weight, maximum heart rate, bike -- are kept with
  their profile, what a
  member allowed to manage one's registrations and photos sees and may do ([accounts](accounts.md)),
  how a guest's region is found from the network provider's location and that the location is not
  stored ([calendar](calendar.md)), how the site counts its own visits -- daily sums only, no cookie,
  address or identifier, the team's pages per member ([statistics](statistics.md)) --, that every
  new member agrees with it on the sign-up form or at a provider's first sign-in, and that a member
  who adds people without accounts answers for having their consent, who sees those people's data
  and what deleting them takes away ([accounts](accounts.md), issue #438) -- and links to the
  contact form.
- **FR-SHL-003**: All rich text (home cards, articles, descriptions) goes through one sanitiser:
  scripts and dangerous links dropped, and every comment, CDATA section, doctype and processing
  instruction, which a browser may end sooner than the sanitiser's parser does, on any Python; a
  link to another page opens in a new tab while one to a part of the same page (`#...`) stays on
  it, a limited set of formatting, image size/float and text colour kept, in time in proportion to
  the text however a colour is written, however deep its tags nest and however many images without
  a safe source it drops, and a text whose tags nest too deep to be written back comes back as plain
  text, escaped
  (`cycling_site/tests.py::SanitizeRichHtmlTests`, `tests/e2e/test_article_contents.py`). Rich text
  stored before the sanitiser dropped them is cleaned once, by `calendar_app` migration 0044: a
  text holding `<!` or `<?` goes through the sanitiser again, and every other keeps its bytes
  (`calendar_app/tests.py::StoredRichTextCommentsMigrationTests`). The deploy runs it while the
  previous release still saves text; what that release saves in between is cleaned only when the
  migration's cleaning runs once more after the deploy, from the shell -- never by unapplying it,
  which unapplies whatever has come to depend on it.
- **FR-SHL-004**: The navbar stays on top with a solid background while scrolling. Its open menu
  wraps whole links and tool groups when needed instead of widening the page, in every locale
  and skin (`tests/e2e/test_interface_rules.py::test_no_tab_scrolls_sideways`).
  A page's heading beside its share button breaks a word too long for the room the button leaves,
  as an event's does, rather than pushing the button off a phone
  (`tests/e2e/test_page_heading_fits.py`). So does an event's description, as an article's body
  does: a chat's name written with commas and no spaces never scrolls a phone sideways
  (`tests/e2e/test_description_fits.py`).
- **FR-SHL-005**: Templates use no multi-line `{# #}` comments (they leak into pages).
- **FR-SHL-006**: Reader-facing names, titles, captions and descriptions are localized data fields
  by default, edited per ru / kk / en in forms and administration. Existing text survives their
  introduction. A document such as a knowledge article may instead belong to one locale and be
  listed only in it. IDs, dates, numbers and URLs are not translated; other exceptions are explicit
  in the area's specification.

## Key Entities

- **SiteContent**: singleton with the navbar title and the home page's tab title per language.
- **HomeCard**: a card of the home page: a heading and a rich text per language, and its position.
- **User.dismissed_hints**: the setup hints a member turned off.

## Local assumptions

Where the code still assumes a place, a brand or a sport (constitution, principle VI):

- **Accepted** (maintainer, 2026-10-21: the three languages are deliberate and a fourth is not planned -- it would mean translating every event and article, beside which naming the three in code costs nothing). The default language is Russian (`LANGUAGE_CODE`). The offered languages are a setting, but the
  three of them are also written into the code one by one: the forms, templates and API schemas
  name each `*_ru` / `*_kk` / `*_en` field (`calendar_app/forms.py`, `news/forms.py`,
  `home/forms.py`, `locations/forms.py`, `api/schemas.py` and their templates), and helpers loop over
  a literal `("ru", "kk", "en")` (`api/endpoints/content.py`, `locations/models.py`,
  `cycling_site/skins.py`). A fourth language would need changes in each.
- The virtual ride page carries its own maps (`trainer/static/trainer/alatau/maps/`, a folder per
  city or region; Almaty and the Almaty Region have routes so far) and the UBT kit its rider wears
  (`data/`). A new map comes with a new revision of the page -- its folder and a line in it; the site
  stores only the route key and name the page sends. Three of the page's words still name Almaty: its title and its
  loading line ("title", "loading" in `text/<lang>.js`) and the site page's description (`trainer/views.py`);
  NEEDS CLARIFICATION: their wording once a second map has routes.
- The fallback page description names countries and sports ("cycling, running, cross-country skiing
  -- in Kazakhstan, Kyrgyzstan, Russia and beyond", `base.html`), and the navbar falls back to
  "Cycling" and the footer to "Cycling events" when the site content has no title.

## API gaps

- The navbar title and the tab title (site content) have no API: the owner edits them on the site only.

## Open Questions

- None known.
