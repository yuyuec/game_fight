"""RM.py

图片与声音资源的统一加载、缓存、查询与释放模块。

本模块提供 ImageSoundResourceManager 类，作为项目中图片（pygame.Surface）
与声音（pygame.mixer.Sound）资源的集中管理入口，避免资源重复加载与引用
泄漏。若项目后续改用其他多媒体后端，只需替换本模块内部的加载调用，
外部调用方无需改动。

约定说明：
1. 缓存键默认使用规范化后的绝对路径，调用方也可以传入自定义 key。
2. 加载失败时不会把错误对象写入缓存，避免后续调用读到无效资源。
"""

from __future__ import annotations

import gc
import logging
import os
from typing import Any, Dict, Optional, Tuple

try:
    import pygame
except ImportError:  # pragma: no cover - 运行环境缺少 pygame 时降级
    pygame = None


__all__ = ["ImageSoundResourceManager"]

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE_DIR = "assets/images"
_DEFAULT_SOUND_DIR = "assets/sounds"


class ImageSoundResourceManager:
    """图片与声音资源的统一管理器。

    该类内部维护两个字典，分别保存 key 到图片对象、key 到声音对象的映射。
    所有对外方法都不直接暴露内部字典，调用方需通过 load/get/release 接口
    操作资源，从而保证缓存状态与音频子系统状态始终一致。
    """

    def __init__(
        self,
        image_dir: str = _DEFAULT_IMAGE_DIR,
        sound_dir: str = _DEFAULT_SOUND_DIR,
        auto_init_mixer: bool = True,
    ) -> None:
        """初始化资源管理器。

        Args:
            image_dir: 图片资源根目录，加载相对路径时以此为基准。
            sound_dir: 声音资源根目录，加载相对路径时以此为基准。
            auto_init_mixer: 是否在初始化时立即初始化音频子系统。
        """
        self.image_dir: str = self._normalize_dir(image_dir)
        self.sound_dir: str = self._normalize_dir(sound_dir)
        self._image_cache: Dict[Any, Any] = {}
        self._sound_cache: Dict[Any, Any] = {}
        self._initialized: bool = False

        if auto_init_mixer:
            try:
                self.init_audio()
            except RuntimeError as exc:
                logger.warning("音频子系统初始化失败，声音资源暂不可用: %s", exc)

    # ------------------------------------------------------------------
    # 路径与前置检查
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_dir(directory: str) -> str:
        """将资源根目录规范化为绝对路径。"""
        if not isinstance(directory, str) or not directory:
            return os.path.abspath(os.getcwd())
        return os.path.normpath(os.path.abspath(directory))

    @staticmethod
    def _resolve_path(path: str, root_dir: str) -> str:
        """把相对路径拼接根目录并规范化为绝对路径。"""
        if not isinstance(path, str) or not path:
            raise ValueError("资源路径必须为非空字符串")
        candidate = path if os.path.isabs(path) else os.path.join(root_dir, path)
        return os.path.normpath(os.path.abspath(candidate))

    @staticmethod
    def _check_file(resolved_path: str) -> None:
        """校验目标路径为存在的文件。"""
        if os.path.isdir(resolved_path):
            raise ValueError(f"资源路径为目录而非文件: {resolved_path}")
        if not os.path.isfile(resolved_path):
            raise FileNotFoundError(f"资源文件不存在: {resolved_path}")

    @staticmethod
    def _require_pygame() -> None:
        """确保 pygame 可用，否则抛出运行时错误。"""
        if pygame is None:
            raise RuntimeError("未安装 pygame，无法加载多媒体资源")

    def _locate_key(
        self, cache: Dict[Any, Any], key: Any, root_dir: str
    ) -> Optional[Any]:
        """在缓存中定位实际使用的键，支持直接传 key 或传路径。"""
        if key in cache:
            return key
        if isinstance(key, str):
            try:
                resolved = self._resolve_path(key, root_dir)
            except ValueError:
                return None
            if resolved in cache:
                return resolved
        return None

    # ------------------------------------------------------------------
    # 音频子系统
    # ------------------------------------------------------------------
    def init_audio(self) -> bool:
        """初始化音频子系统，失败时抛出 RuntimeError。"""
        self._require_pygame()
        if self._initialized:
            return True
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._initialized = True
        except Exception as exc:  # pygame.error 等
            self._initialized = False
            raise RuntimeError(f"音频子系统初始化失败: {exc}") from exc
        return self._initialized

    def _ensure_audio(self) -> None:
        """在加载声音前确保音频子系统已初始化。"""
        if not self._initialized:
            self.init_audio()

    # ------------------------------------------------------------------
    # 图片资源
    # ------------------------------------------------------------------
    def load_image(
        self,
        path: str,
        key: Any = None,
        convert_alpha: bool = False,
    ) -> Any:
        """加载图片并缓存，命中缓存时直接返回已有对象。

        Args:
            path: 图片路径，相对路径以 image_dir 为基准。
            key: 自定义缓存键，为 None 时使用规范化绝对路径。
            convert_alpha: 是否尝试 convert_alpha 优化。

        Returns:
            pygame.Surface 对象。
        """
        resolved = self._resolve_path(path, self.image_dir)
        cache_key = resolved if key is None else key

        cached = self._image_cache.get(cache_key)
        if cached is not None:
            return cached

        self._check_file(resolved)
        self._require_pygame()

        try:
            surface = pygame.image.load(resolved)
        except Exception as exc:
            raise RuntimeError(f"图片加载失败: {resolved}") from exc

        if convert_alpha:
            surface = self._optimize_surface(surface, resolved)

        self._image_cache[cache_key] = surface
        logger.debug("图片已加载并缓存: %s -> %s", resolved, cache_key)
        return surface

    @staticmethod
    def _optimize_surface(surface: Any, resolved: str) -> Any:
        """执行 convert_alpha 优化，显示表面未就绪时安全降级。"""
        try:
            if pygame.display.get_init() and pygame.display.get_surface() is not None:
                return surface.convert_alpha()
            logger.warning("显示表面未初始化，跳过 convert_alpha 优化: %s", resolved)
        except Exception as exc:
            logger.warning("convert_alpha 优化失败，使用原始表面: %s (%s)", resolved, exc)
        return surface

    def get_image(self, key: Any, default: Any = None) -> Any:
        """按 key 查询图片缓存，未命中返回 default（默认 None）。"""
        target = self._locate_key(self._image_cache, key, self.image_dir)
        if target is None:
            return default
        return self._image_cache[target]

    def release_image(self, key: Any) -> bool:
        """释放指定图片，返回是否成功移除。"""
        target = self._locate_key(self._image_cache, key, self.image_dir)
        if target is None:
            return False
        self._image_cache.pop(target, None)
        logger.debug("图片已释放: %s", target)
        return True

    def release_all_images(self) -> None:
        """清空图片缓存，释放全部图片引用。"""
        self._image_cache.clear()
        logger.debug("全部图片缓存已清空")

    # ------------------------------------------------------------------
    # 声音资源
    # ------------------------------------------------------------------
    def load_sound(self, path: str, key: Any = None) -> Any:
        """加载声音并缓存，命中缓存时直接返回已有对象。

        Args:
            path: 声音路径，相对路径以 sound_dir 为基准。
            key: 自定义缓存键，为 None 时使用规范化绝对路径。

        Returns:
            pygame.mixer.Sound 对象。
        """
        resolved = self._resolve_path(path, self.sound_dir)
        cache_key = resolved if key is None else key

        cached = self._sound_cache.get(cache_key)
        if cached is not None:
            return cached

        self._check_file(resolved)
        self._require_pygame()
        self._ensure_audio()

        try:
            sound = pygame.mixer.Sound(resolved)
        except Exception as exc:
            raise RuntimeError(f"声音加载失败: {resolved}") from exc

        self._sound_cache[cache_key] = sound
        logger.debug("声音已加载并缓存: %s -> %s", resolved, cache_key)
        return sound

    def get_sound(self, key: Any, default: Any = None) -> Any:
        """按 key 查询声音缓存，未命中返回 default（默认 None）。"""
        target = self._locate_key(self._sound_cache, key, self.sound_dir)
        if target is None:
            return default
        return self._sound_cache[target]

    def release_sound(self, key: Any) -> bool:
        """停止播放并释放指定声音，返回是否成功移除。"""
        target = self._locate_key(self._sound_cache, key, self.sound_dir)
        if target is None:
            return False
        sound = self._sound_cache.pop(target, None)
        self._stop_sound(sound)
        logger.debug("声音已释放: %s", target)
        return True

    @staticmethod
    def _stop_sound(sound: Any) -> None:
        """安全停止单个声音对象的播放。"""
        if sound is None:
            return
        try:
            sound.stop()
        except Exception as exc:
            logger.warning("停止声音播放失败: %s", exc)

    def release_all_sounds(self) -> None:
        """停止并释放所有声音对象，清空声音缓存。"""
        if pygame is not None:
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.stop()
            except Exception as exc:
                logger.warning("停止全部声音播放失败: %s", exc)
        self._sound_cache.clear()
        logger.debug("全部声音缓存已清空")

    # ------------------------------------------------------------------
    # 统一释放与统计
    # ------------------------------------------------------------------
    def release_all(self) -> None:
        """依次释放图片与声音资源，并建议执行垃圾回收。"""
        self.release_all_images()
        self.release_all_sounds()
        gc.collect()
        logger.debug("全部资源已释放")

    def get_loaded_count(self) -> Tuple[int, int]:
        """返回当前已加载的图片数量和声音数量。"""
        return len(self._image_cache), len(self._sound_cache)

    def has_resource(self, key: Any) -> bool:
        """检查图片缓存或声音缓存中是否存在指定资源。"""
        image_key = self._locate_key(self._image_cache, key, self.image_dir)
        if image_key is not None:
            return True
        return self._locate_key(self._sound_cache, key, self.sound_dir) is not None

    def __repr__(self) -> str:
        image_count, sound_count = self.get_loaded_count()
        return (
            f"{self.__class__.__name__}(image_dir={self.image_dir!r}, "
            f"sound_dir={self.sound_dir!r}, images={image_count}, "
            f"sounds={sound_count}, audio_ready={self._initialized})"
        )