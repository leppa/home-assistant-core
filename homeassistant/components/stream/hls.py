"""Provide functionality to stream HLS."""
from aiohttp import web

from homeassistant.core import callback
from homeassistant.util.dt import utcnow

from .const import FORMAT_CONTENT_TYPE
from .core import PROVIDERS, StreamOutput, StreamView
from .fmp4utils import get_init, get_m4s


@callback
def async_setup_hls(hass):
    """Set up api endpoints."""
    hass.http.register_view(HlsPlaylistView())
    hass.http.register_view(HlsSegmentView())
    hass.http.register_view(HlsInitView())
    return "/api/hls/{}/playlist.m3u8"


class HlsPlaylistView(StreamView):
    """Stream view to serve a M3U8 stream."""

    url = r"/api/hls/{token:[a-f0-9]+}/playlist.m3u8"
    name = "api:stream:hls:playlist"
    cors_allowed = True

    async def handle(self, request, stream, sequence):
        """Return m3u8 playlist."""
        renderer = M3U8Renderer(stream)
        track = stream.add_provider("hls")
        stream.start()
        # Wait for a segment to be ready
        if not track.segments:
            await track.recv()
        headers = {"Content-Type": FORMAT_CONTENT_TYPE["hls"]}
        return web.Response(
            body=renderer.render(track, utcnow()).encode("utf-8"), headers=headers
        )


class HlsInitView(StreamView):
    """Stream view to serve HLS init.mp4."""

    url = r"/api/hls/{token:[a-f0-9]+}/init.mp4"
    name = "api:stream:hls:init"
    cors_allowed = True

    async def handle(self, request, stream, sequence):
        """Return init.mp4."""
        track = stream.add_provider("hls")
        segments = track.get_segment()
        if not segments:
            return web.HTTPNotFound()
        headers = {"Content-Type": "video/mp4"}
        return web.Response(body=get_init(segments[0].segment), headers=headers)


class HlsSegmentView(StreamView):
    """Stream view to serve a HLS fmp4 segment."""

    url = r"/api/hls/{token:[a-f0-9]+}/segment/{sequence:\d+}.m4s"
    name = "api:stream:hls:segment"
    cors_allowed = True

    async def handle(self, request, stream, sequence):
        """Return fmp4 segment."""
        track = stream.add_provider("hls")
        segment = track.get_segment(int(sequence))
        if not segment:
            return web.HTTPNotFound()
        headers = {"Content-Type": "video/iso.segment"}
        return web.Response(
            body=get_m4s(segment.segment, segment.start_pts, int(sequence)),
            headers=headers,
        )


class M3U8Renderer:
    """M3U8 Render Helper."""

    def __init__(self, stream):
        """Initialize renderer."""
        self.stream = stream

    @staticmethod
    def render_preamble(track):
        """Render preamble."""
        return [
            "#EXT-X-VERSION:7",
            f"#EXT-X-TARGETDURATION:{track.target_duration}",
            '#EXT-X-MAP:URI="init.mp4"',
            "#EXT-X-INDEPENDENT-SEGMENTS",
        ]

    @staticmethod
    def render_playlist(track, start_time):
        """Render playlist."""
        segments = track.segments

        if not segments:
            return []

        playlist = ["#EXT-X-MEDIA-SEQUENCE:{}".format(segments[0])]

        for sequence in segments:
            segment = track.get_segment(sequence)
            playlist.extend(
                [
                    "#EXTINF:{:.04f},".format(float(segment.duration)),
                    f"./segment/{segment.sequence}.m4s",
                ]
            )

        return playlist

    def render(self, track, start_time):
        """Render M3U8 file."""
        lines = (
            ["#EXTM3U"]
            + self.render_preamble(track)
            + self.render_playlist(track, start_time)
        )
        return "\n".join(lines) + "\n"


@PROVIDERS.register("hls")
class HlsStreamOutput(StreamOutput):
    """Represents HLS Output formats."""

    @property
    def name(self) -> str:
        """Return provider name."""
        return "hls"

    @property
    def format(self) -> str:
        """Return container format."""
        return "mp4"

    @property
    def audio_codec(self) -> str:
        """Return desired audio codec."""
        return "aac"

    @property
    def video_codecs(self) -> tuple:
        """Return desired video codecs."""
        return {"hevc", "h264"}

    @property
    def container_options(self) -> dict:
        """Return container options."""
        return {"movflags": "frag_custom+empty_moov+default_base_moof"}
