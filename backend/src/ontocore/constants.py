ONTOLOGY_ID = "working"
NS = "https://ontocore.local/ns/working#"
XSD = "http://www.w3.org/2001/XMLSchema#"
LITERAL_RANGE = {
    "text": f"{XSD}string",
    "number": f"{XSD}decimal",
    "date": f"{XSD}date",
}
RANGE_LITERAL = {v: k for k, v in LITERAL_RANGE.items()}
