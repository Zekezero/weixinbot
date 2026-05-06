"""WeChat ilink protocol data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class MessageItemType(IntEnum):
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class MessageType(IntEnum):
    NONE = 0
    USER = 1
    BOT = 2


class MessageState(IntEnum):
    NEW = 0
    GENERATING = 1
    FINISH = 2


class UploadMediaType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class TypingStatus(IntEnum):
    TYPING = 1
    CANCEL = 2


class ILinkBaseModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)


class CDNMedia(ILinkBaseModel):
    encrypt_query_param: str = Field(alias="encryptQueryParam")
    aes_key: str = Field(alias="aesKey")
    encrypt_type: int = Field(default=0, alias="encryptType")
    full_url: str = Field(default="", alias="fullUrl")


class TextItem(ILinkBaseModel):
    text: str


class ImageItem(ILinkBaseModel):
    media: CDNMedia | None = None
    thumb_media: CDNMedia | None = Field(default=None, alias="thumbMedia")
    aeskey: str = ""
    url: str = ""
    mid_size: int = Field(default=0, alias="midSize")
    thumb_size: int = Field(default=0, alias="thumbSize")
    thumb_height: int = Field(default=0, alias="thumbHeight")
    thumb_width: int = Field(default=0, alias="thumbWidth")
    hd_size: int = Field(default=0, alias="hdSize")


class VoiceItem(ILinkBaseModel):
    media: CDNMedia | None = None
    encode_type: int = Field(default=0, alias="encodeType")
    bits_per_sample: int = Field(default=0, alias="bitsPerSample")
    sample_rate: int = Field(default=0, alias="sampleRate")
    playtime: int = Field(default=0, alias="playTime")
    text: str = ""


class FileItem(ILinkBaseModel):
    media: CDNMedia | None = None
    file_name: str = Field(default="", alias="fileName")
    md5: str = ""
    len: str = ""


class VideoItem(ILinkBaseModel):
    media: CDNMedia | None = None
    video_size: int = Field(default=0, alias="videoSize")
    play_length: int = Field(default=0, alias="playLength")
    video_md5: str = Field(default="", alias="videoMd5")
    thumb_media: CDNMedia | None = Field(default=None, alias="thumbMedia")
    thumb_size: int = Field(default=0, alias="thumbSize")
    thumb_height: int = Field(default=0, alias="thumbHeight")
    thumb_width: int = Field(default=0, alias="thumbWidth")


class RefMessage(ILinkBaseModel):
    msg_id: str = Field(default="", alias="msgId")
    text: str = ""
    image_item: ImageItem | None = Field(default=None, alias="imageItem")
    voice_item: VoiceItem | None = Field(default=None, alias="voiceItem")
    file_item: FileItem | None = Field(default=None, alias="fileItem")
    video_item: VideoItem | None = Field(default=None, alias="videoItem")


class MessageItem(ILinkBaseModel):
    type: int
    create_time_ms: int = Field(default=0, alias="createTimeMs")
    update_time_ms: int = Field(default=0, alias="updateTimeMs")
    is_completed: bool = Field(default=False, alias="isCompleted")
    msg_id: str = Field(default="", alias="msgId")
    ref_msg: RefMessage | None = Field(default=None, alias="refMsg")
    text_item: TextItem | None = Field(default=None, alias="textItem")
    image_item: ImageItem | None = Field(default=None, alias="imageItem")
    voice_item: VoiceItem | None = Field(default=None, alias="voiceItem")
    file_item: FileItem | None = Field(default=None, alias="fileItem")
    video_item: VideoItem | None = Field(default=None, alias="videoItem")


class WeixinMessage(ILinkBaseModel):
    seq: int = 0
    message_id: int = Field(default=0, alias="messageId")
    from_user_id: str = Field(default="", alias="fromUserId")
    to_user_id: str = Field(default="", alias="toUserId")
    client_id: str = Field(default="", alias="clientId")
    create_time_ms: int = Field(default=0, alias="createTimeMs")
    update_time_ms: int = Field(default=0, alias="updateTimeMs")
    delete_time_ms: int = Field(default=0, alias="deleteTimeMs")
    session_id: str = Field(default="", alias="sessionId")
    group_id: str = Field(default="", alias="groupId")
    message_type: int = Field(default=0, alias="messageType")
    message_state: int = Field(default=0, alias="messageState")
    item_list: list[MessageItem] = Field(default_factory=list, alias="itemList")
    context_token: str = Field(default="", alias="contextToken")


class BaseInfo(ILinkBaseModel):
    channel_version: str = Field(alias="channelVersion")


class GetUpdatesReq(ILinkBaseModel):
    get_updates_buf: str = Field(alias="getUpdatesBuf")
    base_info: BaseInfo = Field(alias="baseInfo")


class GetUpdatesResp(ILinkBaseModel):
    ret: int = 0
    msgs: list[WeixinMessage] = Field(default_factory=list)
    get_updates_buf: str = Field(default="", alias="getUpdatesBuf")
    longpolling_timeout_ms: int = Field(default=35000, alias="longpollingTimeoutMs")
    errcode: int = 0
    errmsg: str = ""


class SendMessageReq(ILinkBaseModel):
    msg: WeixinMessage
    base_info: BaseInfo = Field(alias="baseInfo")


class GetUploadUrlReq(ILinkBaseModel):
    filekey: str
    media_type: int = Field(alias="mediaType")
    to_user_id: str = Field(alias="toUserId")
    rawsize: int = Field(alias="rawSize")
    rawfilemd5: str = Field(alias="rawFileMd5")
    filesize: int = Field(alias="fileSize")
    no_need_thumb: bool = Field(default=True, alias="noNeedThumb")
    aeskey: str
    base_info: BaseInfo = Field(alias="baseInfo")


class GetUploadUrlResp(ILinkBaseModel):
    ret: int = 0
    upload_full_url: str = Field(default="", alias="uploadFullUrl")
    upload_param: str = Field(default="", alias="uploadParam")
    thumb_upload_param: str = Field(default="", alias="thumbUploadParam")
    errcode: int = 0
    errmsg: str = ""


class GetConfigReq(ILinkBaseModel):
    ilink_user_id: str = Field(alias="ilinkUserId")
    context_token: str = Field(default="", alias="contextToken")
    base_info: BaseInfo = Field(alias="baseInfo")


class GetConfigResp(ILinkBaseModel):
    ret: int = 0
    typing_ticket: str = Field(default="", alias="typingTicket")
    errcode: int = 0
    errmsg: str = ""


class SendTypingReq(ILinkBaseModel):
    ilink_user_id: str = Field(alias="ilinkUserId")
    typing_ticket: str = Field(alias="typingTicket")
    status: int
    base_info: BaseInfo = Field(alias="baseInfo")


class EventType(str, Enum):
    P2P_MESSAGE = "p2p_message"


class MsgType(IntEnum):
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


@dataclass(frozen=True)
class MediaInfo:
    type: MessageItemType
    local_path: str
    mime_type: str = ""
    file_name: str = ""
    duration_ms: int = 0
    transcription: str = ""


@dataclass
class WeixinMsgDTO:
    from_: str
    session_id: str
    text: str
    is_p2p: bool = True
    is_group: bool = False
    file_info: FileItem | None = None
    video_info: VideoItem | None = None
    quote_info: RefMessage | None = None
    media_list: list[MediaInfo] = field(default_factory=list)


@dataclass
class IncomingEvent:
    raw: WeixinMessage
    media_list: list[MediaInfo] = field(default_factory=list)

    @property
    def is_message(self) -> bool:
        return True

    @property
    def event_type(self) -> EventType:
        return EventType.P2P_MESSAGE

    def as_message(self) -> WeixinMsgDTO:
        text = ""
        file_info: FileItem | None = None
        video_info: VideoItem | None = None
        quote_info: RefMessage | None = None

        for item in self.raw.item_list:
            if not quote_info and item.ref_msg:
                quote_info = item.ref_msg
            if not file_info and item.file_item:
                file_info = item.file_item
            if not video_info and item.video_item:
                video_info = item.video_item
            if not text and item.type == MessageItemType.TEXT:
                if item.text_item:
                    text = item.text_item.text
            if not text and item.voice_item and item.voice_item.text:
                text = item.voice_item.text

        return WeixinMsgDTO(
            from_=self.raw.from_user_id,
            session_id=self.raw.from_user_id,
            text=text,
            is_p2p=True,
            is_group=False,
            file_info=file_info,
            video_info=video_info,
            quote_info=quote_info,
            media_list=list(self.media_list),
        )
