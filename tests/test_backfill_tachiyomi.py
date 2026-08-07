"""tachiyomi_page_count / 立ち読み後埋めのテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from db.storageS3 import count_objects_under_prefix, tachiyomi_s3_prefix
from db.trn_dmm_items_repository import resolve_tachiyomi_page_count
from scripts.process import backfill_tachiyomi as bf


class TestResolveTachiyomiPageCount:
    def test_no_url_returns_none(self):
        assert resolve_tachiyomi_page_count(None, 3) is None
        assert resolve_tachiyomi_page_count("", 3) is None

    def test_url_with_uploads(self):
        assert resolve_tachiyomi_page_count("https://example.com/t", 5) == 5

    def test_url_with_zero_uploads(self):
        assert resolve_tachiyomi_page_count("https://example.com/t", 0) == 0


class TestCountObjectsUnderPrefix:
    def test_prefix_format(self):
        assert tachiyomi_s3_prefix("comic", "abc") == "comic/abc/"

    def test_count_returns_len_contents(self):
        with patch("db.storageS3.s3_client") as client:
            client.list_objects_v2.return_value = {
                "Contents": [{"Key": "comic/abc/1.webp"}, {"Key": "comic/abc/2.webp"}]
            }
            assert count_objects_under_prefix("comic", "abc", bucket="b") == 2
            client.list_objects_v2.assert_called_once_with(
                Bucket="b",
                Prefix="comic/abc/",
                MaxKeys=1000,
            )

    def test_count_empty_when_no_contents(self):
        with patch("db.storageS3.s3_client") as client:
            client.list_objects_v2.return_value = {}
            assert count_objects_under_prefix("comic", "abc", bucket="b") == 0

    def test_count_zero_when_bucket_missing(self):
        with patch("db.storageS3.S3_BUCKET", None):
            assert count_objects_under_prefix("comic", "abc", bucket=None) == 0

    def test_count_zero_on_client_error(self):
        from botocore.exceptions import ClientError

        with patch("db.storageS3.s3_client") as client:
            client.list_objects_v2.side_effect = ClientError(
                {"Error": {"Code": "403", "Message": "denied"}},
                "ListObjectsV2",
            )
            assert count_objects_under_prefix("comic", "abc", bucket="b") == 0


class TestInsertSetsPageCount:
    def test_insert_payload_includes_page_count(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": 1}]
        )
        upload = MagicMock(side_effect=["u1", "u2"])

        item = {
            "content_id": "cid1",
            "title": "t",
            "URL": "https://example.com/i",
            "tachiyomi": {"URL": "https://example.com/t"},
            "iteminfo": {},
            "prices": {},
            "imageURL": {},
            "sampleImageURL": {},
        }

        with patch(
            "db.trn_dmm_items_repository.generate_content",
            return_value={"auto_comment": "", "auto_summary": "", "auto_point": ""},
        ):
            with patch(
                "db.trn_dmm_items_repository.execute_with_retry",
                side_effect=lambda builder: builder().execute(),
            ):
                from db.trn_dmm_items_repository import _insert_dmm_item

                _insert_dmm_item(
                    item,
                    ["a.webp", "b.webp"],
                    None,
                    "FANZA",
                    "ebook",
                    "comic",
                    supabase_client=client,
                    upload_local_image_to_s3_fn=upload,
                    coerce_empty_image_urls=True,
                )

        insert_call = client.table.return_value.insert
        payload = insert_call.call_args[0][0]
        assert payload["tachiyomi_page_count"] == 2
        assert payload["tachiyomi_url"] == "https://example.com/t"

    def test_insert_page_count_zero_on_empty_paths(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": 1}]
        )

        item = {
            "content_id": "cid2",
            "title": "t",
            "URL": "https://example.com/i",
            "tachiyomi": {"URL": "https://example.com/t"},
            "iteminfo": {},
            "prices": {},
            "imageURL": {},
            "sampleImageURL": {},
        }

        with patch(
            "db.trn_dmm_items_repository.generate_content",
            return_value={},
        ):
            with patch(
                "db.trn_dmm_items_repository.execute_with_retry",
                side_effect=lambda builder: builder().execute(),
            ):
                from db.trn_dmm_items_repository import _insert_dmm_item

                _insert_dmm_item(
                    item,
                    [],
                    None,
                    "FANZA",
                    "ebook",
                    "novel",
                    supabase_client=client,
                    upload_local_image_to_s3_fn=MagicMock(),
                    coerce_empty_image_urls=True,
                )

        payload = client.table.return_value.insert.call_args[0][0]
        assert payload["tachiyomi_page_count"] == 0

    def test_insert_page_count_null_without_url(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": 1}]
        )

        item = {
            "content_id": "cid3",
            "title": "t",
            "URL": "https://example.com/i",
            "tachiyomi": {},
            "iteminfo": {},
            "prices": {},
            "imageURL": {},
            "sampleImageURL": {},
        }

        with patch(
            "db.trn_dmm_items_repository.generate_content",
            return_value={},
        ):
            with patch(
                "db.trn_dmm_items_repository.execute_with_retry",
                side_effect=lambda builder: builder().execute(),
            ):
                from db.trn_dmm_items_repository import _insert_dmm_item

                _insert_dmm_item(
                    item,
                    [],
                    None,
                    "FANZA",
                    "digital",
                    "videoa",
                    supabase_client=client,
                    upload_local_image_to_s3_fn=MagicMock(),
                    coerce_empty_image_urls=True,
                )

        payload = client.table.return_value.insert.call_args[0][0]
        assert payload["tachiyomi_page_count"] is None


class TestBackfillProcessOneRow:
    def test_sync_when_s3_has_objects(self):
        client = MagicMock()
        row = {
            "content_id": "c1",
            "floor": "comic",
            "tachiyomi_url": "https://example.com/t",
            "title": "t1",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=3):
            with patch.object(bf, "update_tachiyomi_fields", return_value=True) as upd:
                status = bf.process_one_row(
                    row,
                    client=client,
                    upload_fn=MagicMock(),
                    bucket="b",
                    dry_run=False,
                )
        assert status == "synced"
        upd.assert_called_once_with(
            client,
            "c1",
            {"tachiyomi_page_count": 3, "tachiyomi_capture_fail_count": 0},
        )

    def test_capture_and_upload_when_s3_empty(self):
        client = MagicMock()
        row = {
            "content_id": "c2",
            "floor": "novel",
            "tachiyomi_url": "https://example.com/t",
            "title": "t2",
        }
        upload = MagicMock(return_value="https://s3/x")
        with patch.object(bf, "count_objects_under_prefix", return_value=0):
            with patch.object(
                bf, "capture_all_tachiyomi_pages", return_value=["p1.webp", "p2.webp"]
            ):
                with patch.object(bf, "update_tachiyomi_fields", return_value=True) as upd:
                    with patch.object(bf, "cleanup_local_files") as cleanup:
                        status = bf.process_one_row(
                            row,
                            client=client,
                            upload_fn=upload,
                            bucket="b",
                            dry_run=False,
                        )
        assert status == "captured"
        assert upload.call_count == 2
        upd.assert_called_once_with(
            client,
            "c2",
            {"tachiyomi_page_count": 2, "tachiyomi_capture_fail_count": 0},
        )
        cleanup.assert_called_once()

    def test_failed_when_capture_empty_increments_fail_count(self):
        client = MagicMock()
        row = {
            "content_id": "c3",
            "floor": "novel",
            "tachiyomi_url": "https://example.com/t",
            "title": "t3",
            "tachiyomi_capture_fail_count": 1,
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=0):
            with patch.object(bf, "capture_all_tachiyomi_pages", return_value=[]):
                with patch.object(bf, "record_capture_failure", return_value=2) as rec:
                    status = bf.process_one_row(
                        row,
                        client=client,
                        upload_fn=MagicMock(),
                        bucket="b",
                        dry_run=False,
                    )
        assert status == "failed"
        rec.assert_called_once_with(client, "c3", 1)

    def test_dry_run_does_not_capture(self):
        row = {
            "content_id": "c4",
            "floor": "comic",
            "tachiyomi_url": "https://example.com/t",
            "title": "t4",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=0):
            with patch.object(bf, "capture_all_tachiyomi_pages") as capture:
                status = bf.process_one_row(
                    row,
                    client=MagicMock(),
                    upload_fn=MagicMock(),
                    bucket="b",
                    dry_run=True,
                )
        assert status == "captured"
        capture.assert_not_called()

    def test_sync_only_skips_when_s3_empty(self):
        row = {
            "content_id": "c5",
            "floor": "comic",
            "tachiyomi_url": "https://example.com/t",
            "title": "t5",
        }
        with patch.object(bf, "count_objects_under_prefix", return_value=0):
            with patch.object(bf, "capture_all_tachiyomi_pages") as capture:
                status = bf.process_one_row(
                    row,
                    client=MagicMock(),
                    upload_fn=MagicMock(),
                    bucket="b",
                    dry_run=False,
                    sync_only=True,
                )
        assert status == "skipped"
        capture.assert_not_called()


class TestRecordCaptureFailure:
    def test_increments_and_keeps_retryable(self):
        client = MagicMock()
        with patch.object(bf, "update_tachiyomi_fields", return_value=True) as upd:
            assert bf.record_capture_failure(client, "c1", None) == 1
            assert bf.record_capture_failure(client, "c1", 1) == 2
        assert upd.call_count == 2
        assert upd.call_args_list[0].args[2]["tachiyomi_capture_fail_count"] == 1
        assert upd.call_args_list[1].args[2]["tachiyomi_capture_fail_count"] == 2

    def test_reaches_threshold(self):
        client = MagicMock()
        with patch.object(bf, "update_tachiyomi_fields", return_value=True) as upd:
            assert bf.record_capture_failure(client, "c1", 2) == 3
        assert upd.call_args.args[2] == {
            "tachiyomi_page_count": 0,
            "tachiyomi_capture_fail_count": 3,
        }


class TestBackfillRun:
    def test_run_backfill_continues_after_item_error(self):
        rows = [
            {
                "content_id": "ok",
                "floor": "comic",
                "tachiyomi_url": "https://t/1",
                "title": "a",
            },
            {
                "content_id": "bad",
                "floor": "comic",
                "tachiyomi_url": "https://t/2",
                "title": "b",
            },
            {
                "content_id": "ok2",
                "floor": "comic",
                "tachiyomi_url": "https://t/3",
                "title": "c",
            },
        ]

        def process_side_effect(row, **kwargs):
            if row["content_id"] == "bad":
                raise RuntimeError("boom")
            return "synced"

        with patch.object(bf, "resolve_db_target", return_value=(MagicMock(), MagicMock(), "b")):
            with patch.object(bf, "fetch_pending_tachiyomi_rows", return_value=rows):
                with patch.object(bf, "process_one_row", side_effect=process_side_effect):
                    code = bf.run_backfill(db_name="default", limit=10, dry_run=False)

        assert code == 1

    def test_resolve_db_target_unknown(self):
        with pytest.raises(ValueError):
            bf.resolve_db_target("nope")

    def test_parse_args_defaults(self):
        args = bf.parse_args([])
        assert args.db == "default"
        assert args.limit == 20
        assert args.dry_run is False
