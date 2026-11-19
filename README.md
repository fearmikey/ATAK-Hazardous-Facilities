# ATAK High-Consequence Facilities (US)

ATAK-ready KMZ files, one per US state and territory, that pin industrial facilities whose failure, chemical release or compromise could threaten public safety. Everything comes from public EPA and EIA data. The files also work in Google Earth, QGIS or any KML viewer.

**27,353 facilities · 56 states and territories · 6 layers you can turn on and off**

![Legend](docs/legend.png)

## Layers

| Layer | Icon | Source | What's included |
|---|---|---|---|
| Nuclear Power Plants | ☢️ radiation symbol (large, always labeled) | EIA-860/860M | All 55 operating US nuclear plants, with the NRC emergency planning zones noted (10-mile plume, 50-mile ingestion) |
| Chemical / Hazmat | 🔺 red triangle | EPA Risk Management Program (RMP) | Active facilities storing regulated toxic or flammable chemicals above threshold amounts: chemical plants, refineries, ammonia and chlorine users, LPG storage, etc. |
| Heavy Industry / Toxic Releases | ⬢ orange hexagon | EPA Toxics Release Inventory (TRI), 2024 | Smelters, chemical plants, refineries, fuel terminals, paper mills, cement and lime plants, explosives makers, hazardous-waste sites, plus any facility reporting ≥10,000 lb of on-site releases. Sites already in another layer are skipped |
| Drinking Water Treatment | 🔵 blue circle | EPA RMP + EPA ECHO (NPDES permits, SIC 4941) | Water plants storing RMP chemicals (e.g., chlorine gas), plus water-supply facilities holding a discharge permit |
| Wastewater Treatment | 🟫 brown square | EPA RMP + EPA ECHO (major NPDES permits) | Publicly owned treatment works with major permits (generally ≥1 million gallons/day) |
| Power Plants | 🔶 yellow diamond | EIA-860/860M | Non-nuclear plants ≥50 MW: fossil, hydro, pumped storage, biomass, geothermal. Solar, wind and battery sites are excluded |

## What's on each pin

Tap a pin to see:

- Facility name and street address
- Type of operation
- Hazardous chemicals on site, each with its **UN/NA number, ERG 2024 guide number** and a flag if it's **toxic by inhalation (TIH)** or **water-reactive**
- Operator or parent company
- Capacity (MW), design flow (MGD) or 2024 toxic releases (lb), where available
- Source record ID, so you can look it up with EPA or EIA

Example (Nyrstar Clarksville, TN, heavy-industry layer, abridged):

```
Nyrstar Clarksville INC
1800 Zinc Plant Rd, Clarksville, TN 37040

Type: Metal Mining - NAICS 212230
Chemical: Sulfuric acid: UN1830 (ERG 137)
Chemical: Chlorine: UN1017 (ERG 124, TIH)
Chemical: Cadmium And Cadmium Compounds
Carcinogens reported: Yes
On-site releases (2024): 14,286,186 lb
Source: EPA TRI 2024, facility ID 37040SVGZN1800Z
```

Use the UN number to look up health effects and isolation/protective-action distances in the [ERG](https://www.phmsa.dot.gov/hazmat/erg/emergency-response-guidebook-erg) or any ERG-based tool. TIH materials have Table 1 distances in the ERG green pages.

**UN number notes**

- 121 of the 130 RMP chemical names match an ERG entry. The name-to-ERG mapping is in [`data/rmp_to_erg.csv`](data/rmp_to_erg.csv). Every UN and guide number is pulled from the ERG 2024 index ([PubChem ERG table](https://pubchem.ncbi.nlm.nih.gov/erg/), saved as [`data/erg2024_pubchem.tsv`](data/erg2024_pubchem.tsv)).
- Some chemicals have more than one possible UN number depending on form, for example anhydrous HF (`UN1052`) vs. hydrofluoric acid (`UN1790`), or ammonia solutions by strength. RMP doesn't record the form, so the pin lists both.
- Nine RMP chemicals have no UN number: "Flammable Mixture" (mixed hydrocarbons), chlorine dioxide (not shipped as a gas), peracetic acid (depends on formulation), and a few hydrocarbons with no specific ERG entry.
- TRI metal compound groups (e.g., "Lead and lead compounds") have no UN number, because the ERG lists specific substances, not groups.

## Using it in ATAK

1. Download only the state files you need from [`kmz/`](kmz/).
2. In ATAK, open **Import Manager → Local SD** and select the `.kmz`, or copy it to `atak/import/`.
3. Turn layers on and off under **Overlay Manager → File Overlays → *State name***.

> ⚠️ **Don't import every state at once, or import a zip of them.** ATAK will freeze (ANR) trying to load ~27,000 pins. Load a few states at a time.

Labels are hidden by default to keep ATAK responsive. Nuclear plants are the exception. Tap any pin to see its name and details.

## Repository layout

```
kmz/        One KMZ per state/territory (e.g., TN_Tennessee.kmz)
data/       Source data used to build the KMZs, plus summary_by_state.csv
scripts/    fetch_sources.py (downloads fresh data), build_kmz.py (builds the KMZs)
docs/       Legend image
```

## Data sources and currency

| Source | Used for | As of |
|---|---|---|
| EPA Risk Management Program, via the [Data Liberation Project](https://github.com/data-liberation-project/epa-rmp-spreadsheets) | Chemical/hazmat; RMP water, wastewater and power sites | January 2026 |
| [EPA TRI](https://www.epa.gov/toxics-release-inventory-tri-program) basic data | Heavy industry | Reporting year 2024 |
| [EPA ECHO](https://echo.epa.gov/) NPDES permits | Drinking water, wastewater | Pulled November 2026 |
| [EIA-860/860M](https://www.eia.gov/electricity/data/eia860m/) power plants | Nuclear, power | February 2025 |
| [ERG 2024](https://pubchem.ncbi.nlm.nih.gov/erg/) index | UN and guide numbers | 2024 edition |

## Known gaps

- **Drinking water is incomplete.** EPA doesn't publish a national list of drinking water treatment plant locations. This layer only has plants that store RMP chemicals or hold a discharge permit, and coverage varies a lot by state (Wisconsin and Connecticut have very few). Some entries are wells or supply facilities, not full treatment plants.
- **Reporting thresholds apply.** RMP only covers listed chemicals above set amounts, and TRI only covers facilities that meet its reporting thresholds. Facilities that are new, below threshold or not yet reporting won't appear.
- **Sector labels are EPA's.** For example, the Nyrstar Clarksville, TN zinc smelter reports to TRI under metal mining. That's why the heavy-industry layer filters by TRI sector, not industry code.
- **Smaller wastewater plants** (minor permits) aren't included.
- **Positions are as reported to EPA and EIA.** A small number of records had longitude sign errors, which were corrected automatically. Some coordinates may still point to an office or mailing address rather than the plant itself.

## Rebuilding

```bash
pip install -r requirements.txt
python scripts/fetch_sources.py data/
python scripts/build_kmz.py data/rmp kmz data/echo_major_npdes.csv data/eia_power_plants.csv data/echo_drinking_water.csv data/tri2024_facilities.csv
```

`fetch_sources.py` uses only the Python standard library and needs normal internet access. `build_kmz.py` needs Pillow to draw the pin icons. The build:

- Drops deregistered RMP sites and terminated or expired permits.
- Merges facilities that appear in more than one source: RMP vs. ECHO within 500–800 m, RMP vs. EIA within 1.5 km, and TRI vs. any other layer within 400 m.
- Fixes obvious coordinate errors and drops points that fall far outside their state.

## Disclaimer

This is a compilation of public US government data for situational awareness and planning. Records can be outdated, incomplete or mislocated. Verify with the facility, local emergency management or the current ERG before acting on anything here. Inclusion on this map doesn't mean a facility is unsafe or vulnerable.

## License

Scripts are released under the [MIT License](LICENSE). Source data is public information from US federal agencies (EPA, EIA, DOT/PHMSA via PubChem) and is not subject to copyright. The EPA RMP export comes from the [Data Liberation Project](https://github.com/data-liberation-project/epa-rmp-spreadsheets).

## Facilities by state

| State | Nuclear | Chemical/Hazmat | Heavy industry | Drinking water | Wastewater | Power | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Alabama | 2 | 142 | 206 | 108 | 120 | 47 | 625 |
| Alaska | 0 | 44 | 33 | 22 | 20 | 13 | 132 |
| American Samoa | 0 | 0 | 1 | 0 | 1 | 0 | 2 |
| Arizona | 1 | 95 | 97 | 18 | 45 | 37 | 293 |
| Arkansas | 1 | 115 | 121 | 132 | 75 | 29 | 473 |
| California | 1 | 599 | 301 | 114 | 120 | 196 | 1331 |
| Colorado | 0 | 137 | 84 | 135 | 92 | 33 | 481 |
| Connecticut | 1 | 29 | 80 | 2 | 39 | 20 | 171 |
| Delaware | 0 | 18 | 13 | 0 | 2 | 7 | 40 |
| District of Columbia | 0 | 0 | 3 | 1 | 1 | 0 | 5 |
| Florida | 2 | 174 | 209 | 64 | 100 | 71 | 620 |
| Georgia | 2 | 217 | 247 | 70 | 169 | 57 | 762 |
| Guam | 0 | 3 | 5 | 1 | 0 | 0 | 9 |
| Hawaii | 0 | 5 | 20 | 15 | 3 | 11 | 54 |
| Idaho | 0 | 58 | 49 | 10 | 30 | 18 | 165 |
| Illinois | 6 | 807 | 314 | 208 | 211 | 48 | 1594 |
| Indiana | 0 | 345 | 341 | 113 | 149 | 40 | 988 |
| Iowa | 0 | 740 | 138 | 57 | 105 | 29 | 1069 |
| Kansas | 1 | 470 | 100 | 101 | 54 | 23 | 749 |
| Kentucky | 0 | 143 | 144 | 131 | 92 | 28 | 538 |
| Louisiana | 2 | 217 | 182 | 99 | 110 | 49 | 659 |
| Maine | 0 | 37 | 27 | 13 | 56 | 14 | 147 |
| Maryland | 1 | 56 | 41 | 57 | 51 | 18 | 224 |
| Massachusetts | 0 | 61 | 117 | 72 | 34 | 27 | 311 |
| Michigan | 2 | 165 | 279 | 76 | 131 | 42 | 695 |
| Minnesota | 2 | 302 | 156 | 53 | 59 | 29 | 601 |
| Mississippi | 1 | 86 | 113 | 58 | 72 | 23 | 353 |
| Missouri | 1 | 338 | 169 | 161 | 120 | 38 | 827 |
| Montana | 0 | 28 | 36 | 25 | 20 | 20 | 129 |
| Nebraska | 1 | 344 | 59 | 20 | 31 | 18 | 473 |
| Nevada | 0 | 39 | 58 | 8 | 7 | 35 | 147 |
| New Hampshire | 1 | 21 | 32 | 3 | 26 | 8 | 91 |
| New Jersey | 2 | 61 | 151 | 58 | 82 | 26 | 380 |
| New Mexico | 0 | 56 | 46 | 7 | 22 | 15 | 146 |
| New York | 3 | 131 | 174 | 157 | 212 | 77 | 754 |
| North Carolina | 3 | 185 | 227 | 199 | 162 | 36 | 812 |
| North Dakota | 0 | 257 | 50 | 23 | 15 | 15 | 360 |
| Northern Mariana Islands | 0 | 0 | 2 | 1 | 2 | 0 | 5 |
| Ohio | 2 | 348 | 455 | 210 | 195 | 32 | 1242 |
| Oklahoma | 0 | 207 | 143 | 87 | 68 | 40 | 545 |
| Oregon | 0 | 95 | 86 | 5 | 50 | 25 | 261 |
| Pennsylvania | 5 | 271 | 366 | 207 | 224 | 68 | 1141 |
| Puerto Rico | 0 | 18 | 51 | 107 | 38 | 8 | 222 |
| Rhode Island | 0 | 9 | 24 | 4 | 19 | 5 | 61 |
| South Carolina | 4 | 114 | 185 | 70 | 104 | 32 | 509 |
| South Dakota | 0 | 48 | 35 | 102 | 17 | 17 | 219 |
| Tennessee | 2 | 152 | 211 | 157 | 117 | 31 | 670 |
| Texas | 2 | 1044 | 743 | 418 | 568 | 169 | 2944 |
| US Virgin Islands | 0 | 1 | 4 | 5 | 0 | 0 | 10 |
| Utah | 0 | 72 | 74 | 55 | 35 | 15 | 251 |
| Vermont | 0 | 21 | 11 | 0 | 13 | 1 | 46 |
| Virginia | 2 | 107 | 121 | 142 | 82 | 37 | 491 |
| Washington | 1 | 258 | 99 | 28 | 66 | 49 | 501 |
| West Virginia | 0 | 65 | 71 | 116 | 57 | 16 | 325 |
| Wisconsin | 1 | 270 | 249 | 6 | 10 | 35 | 571 |
| Wyoming | 0 | 48 | 43 | 8 | 16 | 14 | 129 |
| **Total** | **55** | **9,673** | **7,396** | **4,119** | **4,319** | **1,791** | **27,353** |
