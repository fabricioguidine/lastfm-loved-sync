from lastfm_loved_sync.normalize import track_key


def test_casefold_and_whitespace():
    assert track_key("Boards Of Canada", "  Roygbiv ") == track_key("boards of canada", "roygbiv")


def test_unicode_normalization():
    # composed vs decomposed accented characters resolve to the same key
    assert track_key("Sigur Rós", "Sæglópur") == track_key("Sigur Rós", "Sæglópur")


def test_distinct_tracks_differ():
    assert track_key("Radiohead", "Reckoner") != track_key("Radiohead", "Nude")
