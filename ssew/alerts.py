"""Turn a flagged zone into immediate, specific controls: what to do before the next shift, tied to the driver
behind the alert and to the legislation that governs it in the site's province.

    BC  Occupational Health and Safety Regulation (OHSR); Workers Compensation Act
    ON  Occupational Health and Safety Act (OHSA); O. Reg. 213/91 Construction Projects; O. Reg. 297/13; O. Reg. 490/09
    AB  Occupational Health and Safety Act; OHS Code

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

LAW = {"BC": "BC OHS Regulation", "ON": "Ontario OHSA and O. Reg. 213/91", "AB": "Alberta OHS Act and OHS Code"}


def recommend(zone, top_drivers, province="BC"):
    """Up to three driver-specific controls plus the zone's standing control, cited for the site's province."""
    acts = [{"driver": d, "action": ACTIONS[d][0], "ref": ACTIONS[d][1][province]} for d in top_drivers if d in ACTIONS][:3]
    z = ZONE_RULE.get(zone)
    if z:
        acts.append({"driver": "Zone standard", "action": z[0], "ref": z[1][province]})
    return acts
