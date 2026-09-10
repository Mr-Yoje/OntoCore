from ontocore.extract.ingress import parse_upload
from ontocore.errors import IngressError


def test_plain_text_blocks():
    doc = parse_upload("a.txt", "标题\n\n第一段。".encode("utf-8"))
    assert doc.filename == "a.txt"
    assert "第一段" in doc.full_text
    assert doc.blocks


def test_unknown_suffix():
    try:
        parse_upload("a.bin", b"x")
    except IngressError:
        return
    raise AssertionError("expected IngressError")


def test_garbage_pdf_raises_ingress_error():
    try:
        parse_upload("a.pdf", b"not a pdf")
    except IngressError as exc:
        assert "无法提取文本" in str(exc)
        return
    raise AssertionError("expected IngressError")


def test_gb18030_txt():
    doc = parse_upload("a.txt", "标题\n\n第一段。".encode("gb18030"))
    assert "第一段" in doc.full_text


def test_undecodable_txt_raises_ingress_error(monkeypatch):
    import ontocore.extract.ingress as ingress

    monkeypatch.setattr(ingress, "_TXT_ENCODINGS", ("utf-8",))
    try:
        parse_upload("a.txt", b"\xff\xfe")
    except IngressError:
        return
    raise AssertionError("expected IngressError")


def test_garbage_docx_raises_ingress_error():
    try:
        parse_upload("a.docx", b"not a docx")
    except IngressError as exc:
        assert "无法提取文本" in str(exc)
        return
    raise AssertionError("expected IngressError")
