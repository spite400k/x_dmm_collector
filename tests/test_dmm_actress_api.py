import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from bs4 import BeautifulSoup

from dmm import dmm_actress_api as api


class FakeResponse:
    def __init__(self, json_data=None, text="", status_code=200):
        self._json = json_data or {}
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            response = MagicMock()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def json(self):
        return self._json


def test_normalize_text():
    assert api._normalize_text(None) is None
    assert api._normalize_text("") is None
    assert api._normalize_text("  abc  ") == "abc"
    assert api._normalize_text(0) == "0"


def test_to_int():
    assert api._to_int(None) is None
    assert api._to_int("") is None
    assert api._to_int("42") == 42
    assert api._to_int("x") is None


def test_parse_iso_date():
    assert api._parse_iso_date(None) is None
    assert api._parse_iso_date("2020-05-01") == "2020-05-01"
    assert api._parse_iso_date("2020-05-01T12:00:00Z") == "2020-05-01"
    assert api._parse_iso_date("invalid") is None


def test_extract_image_filename():
    assert api._extract_image_filename(None) is None
    assert api._extract_image_filename("https://example.com/foo") is None
    assert (
        api._extract_image_filename("https://pics.dmm.co.jp/mono/actjpgs/asami_yuma.jpg")
        == "asami_yuma.jpg"
    )


def test_build_high_res_image_download_url():
    optimizer = (
        "https://image-optimizer.osusume.dmm.co.jp/actress/sample.jpg/width=400"
    )
    assert api.build_high_res_image_download_url(
        image_source_url=optimizer,
        api_image_url="https://pics.dmm.co.jp/mono/actjpgs/sample.jpg",
    ) == "https://image-optimizer.osusume.dmm.co.jp/actress/sample.jpg/width=800"
    assert api.build_high_res_image_download_url(
        api_image_url="https://pics.dmm.co.jp/mono/actjpgs/foo.png",
        width=640,
    ) == "https://image-optimizer.osusume.dmm.co.jp/actress/foo.png/width=640"
    assert api.build_high_res_image_download_url() is None


def test_is_hosted_actress_image():
    with patch.object(api, "S3_PUBLIC_BASE_URL", "https://cdn.example.com"):
        assert api._is_hosted_actress_image("https://cdn.example.com/actress/1.jpg") is True
    assert api._is_hosted_actress_image(
        "https://bucket.s3.amazonaws.com/actress/1.jpg"
    ) is True
    assert api._is_hosted_actress_image("https://pics.dmm.co.jp/x.jpg") is False
    assert api._is_hosted_actress_image(None) is False


def test_upload_actress_image_paths():
    with patch.object(api, "upload_actress_image_to_s3", return_value="https://cdn/a.jpg"):
        record = {"actress_id": 1, "image_url": "https://pics.dmm.co.jp/x.jpg"}
        result = api._upload_actress_image(record)
        assert result["image_url"] == "https://cdn/a.jpg"

    hosted = {"actress_id": 1, "image_url": "https://bucket.s3.amazonaws.com/actress/1.jpg"}
    assert api._upload_actress_image(hosted)["image_url"] == hosted["image_url"]

    assert api._upload_actress_image({"name": "no id"}) == {"name": "no id"}

    with patch.object(api, "build_high_res_image_download_url", return_value=None):
        no_url = {"actress_id": 2, "image_url": "https://pics.dmm.co.jp/x.jpg"}
        assert api._upload_actress_image(no_url) == no_url

    with patch.object(api, "build_high_res_image_download_url", return_value="https://dl/x.jpg"):
        with patch.object(api, "upload_actress_image_to_s3", return_value=None):
            fail = {"actress_id": 3, "image_url": "https://pics.dmm.co.jp/x.jpg"}
            assert api._upload_actress_image(fail) == fail


def test_extract_alias():
    assert api._extract_alias(None) is None
    assert api._extract_alias("山田（やまだ）") == "やまだ"
    assert api._extract_alias("山田(abc)") == "abc"
    assert api._extract_alias("山田") is None


def test_extract_x_account():
    html = """
    <html><body>
      <a href="https://example.com/not-x">other</a>
      <a href="https://x.com/example_user">x</a>
      <a href="https://twitter.com/intent/tweet">share</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert api._extract_x_account(soup) == "example_user"


def test_extract_section_text():
    html = """
    <h2 id="profile-detail">Profile</h2>
    <p>Line1</p>
    <p>Line2</p>
    <h2>Next</h2>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert api._extract_section_text(soup, "profile-detail") == "Line1\nLine2"
    assert api._extract_section_text(soup, "missing") is None


def test_extract_debut_date():
    assert api._extract_debut_date(None) is None
    assert api._extract_debut_date("2020年5月1日デビュー") == "2020-05-01"
    assert api._extract_debut_date("no date") is None


def test_extract_favorite_count():
    assert api._extract_favorite_count("お気に入り登録は 1,234 件") == 1234
    assert api._extract_favorite_count("999人がお気に入り") == 999
    assert api._extract_favorite_count('favorite_count\\":567') == 567
    assert api._extract_favorite_count("none") is None


def test_extract_embedded_field():
    html = 'profile\\":\\"hello\\\\nworld\\"'
    assert api._extract_embedded_field(html, "profile") == "hello\nworld"
    html_num = 'favorite_count\\":123'
    assert api._extract_embedded_field(html_num, "favorite_count") == "123"
    assert api._extract_embedded_field("empty", "missing") is None


def test_dmm_get_success():
    payload = {"result": {"status": "200", "actress": []}}
    with patch("dmm.dmm_actress_api.requests.get", return_value=FakeResponse(payload)):
        result = api._dmm_get("https://example.com", {"a": 1})
        assert result["status"] == "200"


def test_dmm_get_api_error():
    payload = {"result": {"status": "400", "message": "bad request"}}
    with patch("dmm.dmm_actress_api.requests.get", return_value=FakeResponse(payload)):
        with pytest.raises(Exception, match="API error"):
            api._dmm_get("https://example.com", {})


def test_is_unenrichable_name():
    assert api.is_unenrichable_name(None) is True
    assert api.is_unenrichable_name("----") is True
    assert api.is_unenrichable_name("  不明  ") is True
    assert api.is_unenrichable_name("山田花子") is False


def test_fetch_actress_by_id_found():
    payload = {"result": {"status": "200", "actress": [{"id": "1", "name": "A"}]}}
    with patch("dmm.dmm_actress_api._dmm_get", return_value=payload["result"]):
        actress = api.fetch_actress_by_id(1)
        assert actress["name"] == "A"


def test_fetch_actress_by_id_not_found():
    with patch("dmm.dmm_actress_api._dmm_get", return_value={"status": "200", "actress": []}):
        assert api.fetch_actress_by_id(1) is None


def test_fetch_actress_by_keyword():
    assert api.fetch_actress_by_keyword("----") is None
    assert api.fetch_actress_by_keyword("a") is None

    actresses = [
        {"id": "1", "name": "山田", "ruby": "やまだ"},
        {"id": "2", "name": "佐藤", "ruby": "さとう"},
    ]
    with patch("dmm.dmm_actress_api._dmm_get", return_value={"status": "200", "actress": actresses}):
        assert api.fetch_actress_by_keyword("山田")["id"] == "1"

    with patch("dmm.dmm_actress_api._dmm_get", return_value={"status": "200", "actress": []}):
        assert api.fetch_actress_by_keyword("存在しない") is None

    with patch(
        "dmm.dmm_actress_api._dmm_get",
        return_value={"status": "200", "actress": [{"id": "9", "name": "別名", "ruby": "べつ"}]},
    ):
        assert api.fetch_actress_by_keyword("一致なし") is None


def test_fetch_works_count():
    with patch("dmm.dmm_actress_api._dmm_get", return_value={"status": "200", "total_count": "15"}):
        assert api.fetch_works_count(1) == 15


def test_scrape_osusume_profile_success():
    html = """
    <html><body>
      <h2 id="profile-detail">Detail</h2><p>Profile text</p>
      <h2 id="personality">Career</h2><p>Career text</p>
      <h2 id="award">Award</h2><p>Award text</p>
      <a href="https://x.com/actress_x"></a>
      profile\\":\\"embedded profile\\"
      background_and_personality\\":\\"embedded career\\"
      product_and_award\\":\\"fanza\\"
      activity_period_from\\":\\"2019-01-02\\"
      favorite_count\\":100
      name_en\\":\\"Yuki\\"
      alias\\":\\"Alias\\"
      image_url\\":\\"https://image-optimizer.osusume.dmm.co.jp/actjpgs/p.jpg/width=400\\"
    </body></html>
    """
    session = MagicMock()
    session.get.return_value = FakeResponse(text=html)

    data = api.scrape_osusume_profile(10, session=session)
    assert data["profile"] == "embedded profile"
    assert data["career_text"] == "embedded career"
    assert data["fanza_activity"] == "fanza"
    assert data["awards"] == "Award text"
    assert data["x_account"] == "actress_x"
    assert data["debut_date"] == "2019-01-02"
    assert data["favorite_count"] == 100
    assert data["name_en"] == "Yuki"
    assert data["alias"] == "Alias"
    assert "image_source_url" in data


def test_scrape_osusume_profile_404():
    session = MagicMock()
    response = FakeResponse(status_code=404)
    exc = requests.HTTPError(response=response)
    session.get.side_effect = exc

    assert api.scrape_osusume_profile(10, session=session) == {}


def test_scrape_osusume_profile_request_error():
    session = MagicMock()
    session.get.side_effect = requests.Timeout("timeout")

    assert api.scrape_osusume_profile(10, session=session) == {}


def test_scrape_osusume_profile_closes_own_session():
    html = "<html><body></body></html>"
    with patch.object(api, "_create_session") as create_session:
        session = MagicMock()
        session.get.return_value = FakeResponse(text=html)
        create_session.return_value = session
        api.scrape_osusume_profile(1)
        session.close.assert_called_once()


def test_map_api_actress_to_record():
    api_actress = {
        "id": "123",
        "name": "山田（やま）",
        "ruby": "やまだ",
        "imageURL": {"large": "https://pics.dmm.co.jp/l.jpg", "small": "https://pics.dmm.co.jp/s.jpg"},
        "bust": "90",
        "cup": "F",
        "waist": "60",
        "hip": "88",
        "height": "160",
        "birthday": "1990-01-01",
        "blood_type": "A",
        "hobby": "読書",
        "prefectures": "東京",
    }
    record = api.map_api_actress_to_record(api_actress)
    assert record["actress_id"] == 123
    assert record["alias"] == "やま"
    assert record["image_url"] == "https://pics.dmm.co.jp/l.jpg"


def test_merge_scrape_and_works():
    record = {"actress_id": 1, "alias": "existing"}
    scrape = {
        "profile": "p",
        "alias": "new",
        "career_text": "c",
    }
    with patch.object(api, "scrape_osusume_profile", return_value=scrape):
        with patch.object(api, "fetch_works_count", return_value=5):
            merged = api._merge_scrape_and_works(record, 1, session=MagicMock())
    assert merged["profile"] == "p"
    assert merged["alias"] == "existing"
    assert merged["works_count"] == 5


def test_enrich_actress_via_api():
    api_actress = {"id": "5", "name": "Test", "imageURL": {"large": "https://pics.dmm.co.jp/x.jpg"}}
    merged = {"actress_id": 5, "name": "Test", "profile": "p"}

    with patch.object(api, "fetch_actress_by_id", return_value=api_actress):
        with patch.object(api, "_merge_scrape_and_works", return_value=merged):
            with patch.object(api, "_upload_actress_image", side_effect=lambda r: r):
                with patch("dmm.dmm_actress_api.time.sleep") as sleep_mock:
                    result = api.enrich_actress(5, request_interval=1.0)
                    assert result["profile"] == "p"
                    sleep_mock.assert_called_once_with(1.0)


def test_enrich_actress_keyword_fallback():
    api_actress = {"id": "6", "name": "Fallback", "imageURL": {}}
    merged = {"actress_id": 6, "name": "Fallback", "works_count": 1}

    with patch.object(api, "fetch_actress_by_id", return_value=None):
        with patch.object(api, "fetch_actress_by_keyword", return_value=api_actress):
            with patch.object(api, "_merge_scrape_and_works", return_value=merged):
                with patch.object(api, "_upload_actress_image", side_effect=lambda r: r):
                    result = api.enrich_actress(6, name="Fallback", request_interval=0)
                    assert result["works_count"] == 1


def test_enrich_actress_scrape_only():
    merged = {"actress_id": 7, "profile": "only scrape"}

    with patch.object(api, "fetch_actress_by_id", return_value=None):
        with patch.object(api, "fetch_actress_by_keyword", return_value=None):
            with patch.object(api, "_merge_scrape_and_works", return_value=merged):
                with patch.object(api, "_upload_actress_image", side_effect=lambda r: r):
                    result = api.enrich_actress(7, request_interval=0)
                    assert result["profile"] == "only scrape"


def test_enrich_actress_no_data():
    with patch.object(api, "fetch_actress_by_id", return_value=None):
        with patch.object(api, "fetch_actress_by_keyword", return_value=None):
            with patch.object(api, "_merge_scrape_and_works", return_value={"actress_id": 8}):
                assert api.enrich_actress(8, request_interval=0) is None


def test_create_session():
    session = api._create_session()
    assert session.cookies.get("age_check_done", domain=".dmm.co.jp") == "1"
    session.close()
