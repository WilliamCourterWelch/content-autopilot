import unittest

from scripts.formats import (
    DEFAULT_AI_LANE_FORMATS,
    STUDIO_FORMATS,
    UnknownFormatError,
    canonicalize_format,
    format_spec,
    parse_formats,
)


class ParseFormatsTests(unittest.TestCase):
    def test_default_is_single_audio_canary(self):
        self.assertEqual(parse_formats(None), ["audio"])
        self.assertEqual(parse_formats(""), ["audio"])
        self.assertEqual(parse_formats("   "), ["audio"])
        self.assertEqual(DEFAULT_AI_LANE_FORMATS, ("audio",))

    def test_comma_list(self):
        self.assertEqual(
            parse_formats("audio,report,infographic"),
            ["audio", "report", "infographic"],
        )

    def test_aliases_and_dedupe(self):
        self.assertEqual(
            parse_formats("slides, slide_deck, podcast, mindmap, flash-cards"),
            ["slide-deck", "audio", "mind-map", "flashcards"],
        )

    def test_all_expands(self):
        self.assertEqual(parse_formats("all"), list(STUDIO_FORMATS))
        self.assertEqual(parse_formats("*"), list(STUDIO_FORMATS))

    def test_unknown_raises(self):
        with self.assertRaises(UnknownFormatError):
            parse_formats("audio,tiktok")

    def test_iterable_input(self):
        self.assertEqual(parse_formats(["video", "quiz"]), ["video", "quiz"])

    def test_video_format_is_canonical(self):
        self.assertEqual(parse_formats("video"), ["video"])
        spec = format_spec("video")
        self.assertEqual(spec["cli"], "video")
        self.assertEqual(spec["generate"], "generate_video")

    def test_cinematic_video_aliases_to_video(self):
        self.assertEqual(parse_formats("cinematic-video"), ["video"])
        self.assertEqual(canonicalize_format("cinematic_video"), "video")

    def test_canonical_cli_names(self):
        for name in STUDIO_FORMATS:
            spec = format_spec(name)
            self.assertEqual(spec["name"], name)
            self.assertEqual(spec["cli"], name)
            self.assertTrue(spec["generate"].startswith("generate_"))
            self.assertTrue(spec["download"].startswith("download_"))

    def test_canonicalize(self):
        self.assertEqual(canonicalize_format("SLIDE DECK"), "slide-deck")
        with self.assertRaises(UnknownFormatError):
            canonicalize_format("all")


if __name__ == "__main__":
    unittest.main()
