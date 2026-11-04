"""Turn a flagged zone into immediate, specific controls: what to do before the next shift, tied to the driver
behind the alert and to the legislation that governs it in the site's province.

    BC  Occupational Health and Safety Regulation (OHSR); Workers Compensation Act
    ON  Occupational Health and Safety Act (OHSA); O. Reg. 213/91 Construction Projects; O. Reg. 297/13; O. Reg. 490/09
    AB  Occupational Health and Safety Act; OHS Code
    The other 10: see LAWS below. citations.py gives the exact section, heading and a plain summary wherever one has been checked; other controls keep the instrument and topic.

References point the site's competent person to the governing provision; always check the current text."""

ACTIONS = {  # driver -> (control, {province: reference})
    "Near-miss reports": ("Stand-down toolbox talk on this zone's recent near misses; supervisor walks the zone before start",
                          {"BC": "OHSR Part 3: inspections and investigations", "ON": "OHSA s.9: joint health and safety committee",
                           "AB": "OHS Act: incident reporting and investigation"}),
    "Hazard observations": ("Close out every open hazard observation before work starts; add a mid-shift inspection",
                            {"BC": "OHSR Part 3: workplace inspections", "ON": "OHSA s.9: workplace inspections",
                             "AB": "OHS Code Part 2: hazard assessment and control"}),
    "PPE non-compliance": ("PPE check at zone entry; replace damaged harnesses, eyewear and gloves",
                           {"BC": "OHSR Part 8: personal protective equipment", "ON": "O. Reg. 213/91: protective clothing and equipment",
                            "AB": "OHS Code Part 18: personal protective equipment"}),
    "Housekeeping": ("Dedicated clean-up crew: clear debris, cords and offcuts from walkways and access routes",
                     {"BC": "OHSR Part 4: general conditions", "ON": "O. Reg. 213/91: housekeeping and access",
                      "AB": "OHS Act: employer general duties"}),
    "New workers on crew": ("Pair every new worker with an experienced buddy; confirm site orientation is complete",
                            {"BC": "OHSR Part 3: young or new workers (3.22–3.25)", "ON": "O. Reg. 297/13: mandatory training",
                             "AB": "OHS Act: worker training and orientation"}),
    "Overtime and fatigue": ("Cap overtime and rotate crews; fatigue check in the pre-shift meeting",
                             {"BC": "OHSR Part 4: impairment", "ON": "OHSA s.25(2)(h): employer general duty",
                              "AB": "OHS Code Part 2: hazard assessment (fatigue)"}),
    "Trade congestion": ("Re-sequence trades so one trade works each bay; settle conflicts at the coordination meeting",
                         {"BC": "Workers Compensation Act: prime contractor coordination", "ON": "OHSA s.23: constructor duties",
                          "AB": "OHS Act: prime contractor duties"}),
    "Permit issues": ("Audit open permits (hot work, excavation, critical lifts) and stop work without a valid permit",
                      {"BC": "OHSR Parts 12, 14 and 20", "ON": "O. Reg. 213/91: excavations, hoisting and hot work",
                       "AB": "OHS Code Parts 6, 10 and 32"}),
    "Wind forecast": ("Stand down crane lifts above the manufacturer's wind limit; secure sheeting, panels and loose material",
                      {"BC": "OHSR Part 14: cranes and hoists; Part 13: scaffolds", "ON": "O. Reg. 213/91: cranes, hoisting and rigging",
                       "AB": "OHS Code Part 6: cranes; Part 23: scaffolds"}),
    "Heat forecast": ("Heat-stress plan: water, shade and work-rest cycles; start earlier and move heavy work to the morning",
                      {"BC": "OHSR Part 7: thermal exposure", "ON": "OHSA s.25(2)(h); ministry heat stress guidance",
                       "AB": "OHS Code Part 2: hazard assessment (heat stress)"}),
    "Rain and ice forecast": ("Sand or salt decks, ramps and ladders; check edge protection and anchors after the weather",
                              {"BC": "OHSR Part 4: general conditions; Part 11: fall protection", "ON": "O. Reg. 213/91: fall protection (s.26)",
                               "AB": "OHS Code Part 9: fall protection"}),
    "Extreme cold forecast": ("Work/warm-up schedule, heated shelter and buddy checks; cover skin and keep tools and walkways clear of ice",
                              {"BC": "OHSR Part 7: thermal exposure", "ON": "OHSA s.25(2)(h): employer general duty", "AB": "OHS Code Part 2: hazard assessment (cold stress)"}),
    "Crew exposure": ("Raise the supervision ratio for the peak crew; brief the day's highest-risk tasks",
                      {"BC": "OHSR Part 3: supervision", "ON": "OHSA s.27: supervisor duties", "AB": "OHS Act: supervisor duties"}),
}

ZONE_RULE = {  # the zone's standing control, added to every alert there
    "EXC": ("Inspect shoring and sloping; keep spoil and equipment back from the edge",
            {"BC": "OHSR Part 20: excavations", "ON": "O. Reg. 213/91 Part III: excavations", "AB": "OHS Code Part 32: excavating and tunnelling"}),
    "CRN": ("Confirm the lift plan, exclusion zone and signaller for every lift",
            {"BC": "OHSR Part 14: cranes and hoists", "ON": "O. Reg. 213/91: cranes, hoisting and rigging", "AB": "OHS Code Part 6: cranes, hoists and lifting devices"}),
    "FRM": ("Check formwork bracing and the pour sequence; keep workers clear of the pump boom",
            {"BC": "OHSR Part 20: concrete formwork", "ON": "O. Reg. 213/91: forms, formwork and falsework", "AB": "OHS Code Part 2: hazard assessment"}),
    "DCK": ("Verify guardrails and covered openings on every open edge",
            {"BC": "OHSR Part 11: fall protection", "ON": "O. Reg. 213/91: fall protection (s.26) and guardrails", "AB": "OHS Code Part 9: fall protection"}),
    "SCF": ("Scaffold tag check: inspected, tied in, fully planked, guardrails on",
            {"BC": "OHSR Part 13: scaffolds", "ON": "O. Reg. 213/91: scaffolds", "AB": "OHS Code Part 23: scaffolds and temporary work platforms"}),
    "ROF": ("Fall-arrest anchors and warning lines in place before roof access",
            {"BC": "OHSR Part 11: fall protection", "ON": "O. Reg. 213/91: fall protection (s.26)", "AB": "OHS Code Part 9: fall protection"}),
    "MEP": ("Lock out and test before work on circuits; fire watch for hot work",
            {"BC": "OHSR Part 19: electrical safety", "ON": "O. Reg. 213/91: electrical hazards", "AB": "OHS Code Part 15: hazardous energy; Part 17: power lines"}),
    "INT": ("Dust control for cutting and grinding; clear stair and corridor routes",
            {"BC": "OHSR Part 6: silica", "ON": "O. Reg. 490/09: designated substances (silica)", "AB": "OHS Code Part 4: harmful substances (silica)"}),
    "GTE": ("Traffic control person and separated pedestrian route at the gate",
            {"BC": "OHSR Part 18: traffic control", "ON": "O. Reg. 213/91: traffic protection and signallers", "AB": "OHS Code Part 19: powered mobile equipment"}),
    "LAY": ("Mechanical lifting aids for heavy loads; stack material stable and low",
            {"BC": "OHSR Part 4: ergonomics", "ON": "OHSA s.25(2)(h): musculoskeletal disorder prevention", "AB": "OHS Code Part 14: lifting and handling loads"}),
}

import re
from . import citations

# name of the act and the main regulation for the other 10 jurisdictions
LAWS = {
    "QC": ("Act respecting occupational health and safety", "Safety Code for the construction industry", "Quebec AOHS and Safety Code for the construction industry"),
    "MB": ("Workplace Safety and Health Act", "Workplace Safety and Health Regulation (M.R. 217/2006)", "Manitoba Workplace Safety and Health Act and M.R. 217/2006"),
    "SK": ("Saskatchewan Employment Act, Part III", "Occupational Health and Safety Regulations, 2020", "The Saskatchewan Employment Act and OHS Regulations, 2020"),
    "NS": ("Occupational Health and Safety Act", "Workplace Health and Safety Regulations", "Nova Scotia OHS Act and Workplace Health and Safety Regulations"),
    "NB": ("Occupational Health and Safety Act", "General Regulation 91-191", "New Brunswick OHS Act and General Regulation 91-191"),
    "NL": ("Occupational Health and Safety Act", "OHS Regulations, 2012", "Newfoundland and Labrador OHS Act and OHS Regulations, 2012"),
    "PE": ("Occupational Health and Safety Act", "OHS General Regulations", "PEI OHS Act and OHS General Regulations"),
    "YT": ("Workers' Safety and Compensation Act", "Occupational Health and Safety Regulations", "Yukon Workers' Safety and Compensation Act and OHS Regulations"),
    "NT": ("Safety Act", "Occupational Health and Safety Regulations (R-039-2015)", "Northwest Territories Safety Act and OHS Regulations"),
    "NU": ("Safety Act", "Occupational Health and Safety Regulations (Nu Reg 003-2016)", "Nunavut Safety Act and OHS Regulations"),
}
LAW = {"BC": "BC OHS Regulation", "ON": "Ontario OHSA and O. Reg. 213/91", "AB": "Alberta OHS Act and OHS Code", **{k: v[2] for k, v in LAWS.items()}}
# which instrument governs a control, and the topic to look up there: "act" = duties in the act, "reg" = the regulation
TOPICS = {
    "Near-miss reports": ("act", "incident reporting and investigation"), "Hazard observations": ("act", "workplace inspections and joint committee"),
    "PPE non-compliance": ("reg", "personal protective equipment"), "Housekeeping": ("reg", "housekeeping and safe access"),
    "New workers on crew": ("act", "worker orientation, training and supervision"), "Overtime and fatigue": ("act", "employer's general duty"),
    "Trade congestion": ("act", "coordination duties of the prime contractor or constructor"), "Permit issues": ("reg", "excavation, hoisting and hot work"),
    "Wind forecast": ("reg", "cranes, hoists and scaffolds"), "Heat forecast": ("act", "employer's general duty (thermal stress)"),
    "Rain and ice forecast": ("reg", "fall protection and safe surfaces"), "Extreme cold forecast": ("act", "employer's general duty (cold stress)"),
    "Crew exposure": ("act", "supervisor duties"),
    "EXC": ("reg", "excavations and trenches"), "CRN": ("reg", "cranes, hoists and rigging"), "FRM": ("reg", "formwork and concrete"),
    "DCK": ("reg", "fall protection and guardrails"), "SCF": ("reg", "scaffolds and work platforms"), "ROF": ("reg", "fall protection"),
    "MEP": ("reg", "electrical safety, lockout and hot work"), "INT": ("reg", "harmful dust and substances, including silica"), "GTE": ("reg", "traffic control and mobile equipment"),
    "LAY": ("reg", "manual handling and material storage"),
}
# Nova Scotia splits these topics across three regulations; the Workplace Health and Safety Regulations hold fall protection and scaffolds
NS_GENERAL = {"EXC", "CRN", "FRM", "MEP", "LAY", "Wind forecast", "Permit issues", "PPE non-compliance", "Housekeeping"}
# Yukon publishes its regulations by part, so citations can name the part
YT_PART = {"PPE non-compliance": 1, "Housekeeping": 1, "Permit issues": 10, "Wind forecast": 5, "Rain and ice forecast": 1, "EXC": 10, "CRN": 5, "FRM": 10, "DCK": 1, "SCF": 10, "ROF": 1, "MEP": 9, "GTE": 6, "LAY": 8}
for table in (ACTIONS, ZONE_RULE):
    for key, (_, refs) in table.items():
        kind, topic = TOPICS[key]
        for j, (act, reg, _) in LAWS.items():
            refs[j] = f"{act if kind == 'act' else reg}: {topic}"
        if key in NS_GENERAL:
            refs["NS"] = f"Occupational Safety General Regulations: {topic}"
        if key == "INT":
            refs["NS"] = f"Occupational Health Regulations: {topic}"
            refs["YT"] = f"Workplace Health Regulations: {topic}"
        if key in YT_PART:
            refs["YT"] = f"Occupational Health and Safety Regulations Part {YT_PART[key]}: {topic}"

# official texts, each opened and checked (November 2026)
WSBC = "https://www.worksafebc.com/en/law-policy/occupational-health-safety/searchable-ohs-regulation/"
BC_PARTS = {3: "part-03-rights-and-responsibilities", 4: "part-04-general-conditions", 6: "part-06-substance-specific-requirements", 7: "part-07-noise-vibration-radiation-and-temperature", 8: "part-08-personal-protective-clothing-and-equipment",
            11: "part-11-fall-protection", 12: "part-12-tools-machinery-and-equipment", 13: "part-13-ladders-scaffolds-and-temporary-work-platforms", 14: "part-14-cranes-and-hoists", 18: "part-18-traffic-control", 19: "part-19-electrical-safety", 20: "part-20-construction-excavation-and-demolition"}
YT_URL = {1: "part-1-general", 5: "part-5-cranes-hoisting-and-lifting", 6: "part-6-mobile-equipment", 8: "part-8-material-and-storage", 9: "part-9-electrical-safety", 10: "part-10-construction-and-building-safety"}
LINKS = {  # act, main regulation, further instruments as (name, url)
    "BC": [("Workers Compensation Act", WSBC + "workers-compensation-act"), ("OHS Regulation", WSBC + "ohs-regulation/part-03-rights-and-responsibilities")],
    "AB": [("OHS Act", "https://open.alberta.ca/publications/o02p2"), ("OHS Code", "https://kings-printer.alberta.ca/documents/OHS/OHSCode.pdf")],
    "SK": [("Saskatchewan Employment Act", "https://publications.saskatchewan.ca//api/v1/products/70351/formats/78194/download"), ("OHS Regulations, 2020", "https://publications.saskatchewan.ca/api/v1/products/112399/formats/126367/download")],
    "MB": [("Workplace Safety and Health Act", "https://web2.gov.mb.ca/laws/statutes/ccsm/w210.php"), ("Regulation M.R. 217/2006", "https://web2.gov.mb.ca/laws/regs/current/_pdf-regs.php?reg=217/2006")],
    "ON": [("OHSA", "https://www.ontario.ca/laws/statute/90o01"), ("O. Reg. 213/91, construction projects", "https://www.ontario.ca/laws/regulation/910213"), ("O. Reg. 297/13, training", "https://www.ontario.ca/laws/regulation/130297"), ("O. Reg. 490/09, designated substances", "https://www.ontario.ca/laws/regulation/090490")],
    "QC": [("Act respecting occupational health and safety", "https://www.legisquebec.gouv.qc.ca/en/document/cs/S-2.1"), ("Safety Code for the construction industry", "https://www.legisquebec.gouv.qc.ca/en/document/cr/S-2.1,%20r.%204")],
    "NB": [("OHS Act", "https://laws.gnb.ca/en/document/cs/O-0.2"), ("General Regulation 91-191", "https://laws.gnb.ca/en/document/cr/91-191")],
    "NS": [("OHS Act", "https://nslegislature.ca/sites/default/files/legc/statutes/occupational%20health%20and%20safety.pdf"), ("Workplace Health and Safety Regulations", "https://novascotia.ca/just/regulations/regs/ohsworkplace.htm"), ("Occupational Safety General Regulations", "https://novascotia.ca/just/regulations/regs/ohsgensf.htm"), ("Occupational Health Regulations", "https://novascotia.ca/lae/healthandsafety/docs/occupationalhealthregs.pdf")],
    "PE": [("OHS Act", "https://www.princeedwardisland.ca/en/legislation/occupational-health-and-safety-act"), ("OHS General Regulations", "https://www.princeedwardisland.ca/sites/default/files/legislation/o1-01g-occupational_health_and_safety_act_general_regulations.pdf")],
    "NL": [("OHS Act", "https://www.assembly.nl.ca/legislation/sr/statutes/o03.htm"), ("OHS Regulations, 2012", "https://www.assembly.nl.ca/legislation/sr/regulations/rc120005.htm")],
    "YT": [("Workers' Safety and Compensation Act", "https://www.wcb.yk.ca/web-0070/web-0137"), ("OHS Regulations, by part", "https://www.wcb.yk.ca/regulations"), ("Official versions", "https://yukon.ca/en/find-legislation")],
    "NT": [("Safety Act", "https://gnwt.ca/sites/default/files/legacy_justice/files/legislation/safety/safety.a.pdf"), ("OHS Regulations (R-039-2015)", "https://www.justice.gov.nt.ca/en/files/legislation/safety/safety.r8.pdf")],
    "NU": [("Safety Act", "https://www.nunavutlegislation.ca/en/consolidated-law/safety-act-consolidation"), ("OHS Regulations (not updated for R-007-2025 and R-041-2025)", "https://www.nunavutlegislation.ca/en/consolidated-law/occupational-health-and-safety-regulations-official-consolidation")],
}


# exact sections replace the topic citation wherever one has been read and checked
REF_URL, REF_SUM = {j: {} for j in LINKS}, {j: {} for j in LINKS}
for table in (ACTIONS, ZONE_RULE):
    for key, (_, refs) in table.items():
        for j in LINKS:
            c = citations.cite(j, key)
            if c:
                refs[j], REF_URL[j][c[0]] = c[0], c[1]
                REF_SUM[j][c[0]] = c[2]


def ref_url(j, ref):
    """The official text behind a citation."""
    if ref in REF_URL[j]:
        return REF_URL[j][ref]
    L = LINKS[j]
    if j == "BC":
        m = re.search(r"Parts? (\d+)", ref)
        return WSBC + "ohs-regulation/" + BC_PARTS[int(m.group(1))] if m and int(m.group(1)) in BC_PARTS else L[0][1]
    if j == "ON":
        return next((u for k, u in (("213/91", L[1][1]), ("297/13", L[2][1]), ("490/09", L[3][1])) if k in ref), L[0][1])
    if j == "AB":
        return L[1][1] if "Code" in ref else L[0][1]
    if j == "NS":
        return L[2][1] if "General Regulations" in ref else L[3][1] if "Occupational Health Regulations" in ref else L[1][1] if ref.startswith("Workplace") else L[0][1]
    if j == "YT":
        m = re.search(r"Part (\d+)", ref)
        return "https://www.wcb.yk.ca/regulations/" + (YT_URL[int(m.group(1))] if m else "occupational-health-regulations") if m or "Workplace Health" in ref else L[0][1]
    return L[0][1] if ref.startswith(LAWS[j][0]) else L[1][1]


def ref_links():
    return {j: {r[j]: ref_url(j, r[j]) for t in (ACTIONS, ZONE_RULE) for _, r in t.values()} for j in LINKS}


def recommend(zone, top_drivers, province="BC"):
    """Up to three driver-specific controls plus the zone's standing control, cited for the site's jurisdiction."""
    acts = [{"driver": d, "action": ACTIONS[d][0], "ref": ACTIONS[d][1][province]} for d in top_drivers if d in ACTIONS][:3]
    z = ZONE_RULE.get(zone)
    if z:
        acts.append({"driver": "Zone standard", "action": z[0], "ref": z[1][province]})
    return acts