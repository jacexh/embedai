# MCAP 预览功能测试设计方案

## 1. 测试分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        E2E 测试层                                │
│  (Playwright/pytest - 完整用户场景)                              │
├─────────────────────────────────────────────────────────────────┤
│                      集成测试层                                  │
│  (真实服务 + 真实 MCAP 文件 + TestContainers)                    │
├─────────────────────────────────────────────────────────────────┤
│                      单元测试层                                  │
│  (Mock 依赖 - 逻辑验证)                                          │
├─────────────────────────────────────────────────────────────────┤
│                      前端测试层                                  │
│  (Jest + React Testing Library + MSW)                           │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 后端单元测试

### 2.1 Frame Extractor 单元测试
**文件**: `services/dataset-service/tests/test_frame_extractor.py`

```python
"""Frame extractor unit tests with mocked MCAP dependencies."""

class TestMcapFrameExtractorInit:
    """测试初始化逻辑"""

    def test_init_with_string_path(self):
        """使用字符串路径初始化"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        assert extractor.file_path == Path("/tmp/test.mcap")

    def test_init_with_path_object(self):
        """使用 Path 对象初始化"""
        extractor = McapFrameExtractor(Path("/tmp/test.mcap"))
        assert extractor.file_path == Path("/tmp/test.mcap")

    def test_typestore_initialization(self):
        """验证 ROS1 typestore 正确加载"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        assert extractor._typestore is not None
        assert 'sensor_msgs/msg/CompressedImage' in extractor._typestore.types
        assert 'sensor_msgs/msg/Image' in extractor._typestore.types


class TestGetImageTopics:
    """测试图像 topic 识别"""

    def test_get_image_topics_with_ros1_compressed(self, mock_mcap_reader):
        """识别 ROS1 CompressedImage topic"""
        # Mock summary with ros1msg encoding
        reader = mock_mcap_reader(
            channels=[
                {
                    'id': 1,
                    'topic': '/camera/compressed',
                    'schema_id': 1,
                    'message_encoding': 'ros1'
                }
            ],
            schemas=[
                {
                    'id': 1,
                    'name': 'sensor_msgs/msg/CompressedImage',
                    'encoding': 'ros1msg'
                }
            ]
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1
        assert topics[0]['name'] == '/camera/compressed'
        assert topics[0]['type'] == 'compressed_image'
        assert topics[0]['schema_name'] == 'sensor_msgs/msg/CompressedImage'

    def test_get_image_topics_with_ros1_raw(self, mock_mcap_reader):
        """识别 ROS1 Image topic"""
        reader = mock_mcap_reader(
            channels=[{
                'id': 1,
                'topic': '/camera/raw',
                'schema_id': 1,
                'message_encoding': 'ros1'
            }],
            schemas=[{
                'id': 1,
                'name': 'sensor_msgs/msg/Image',
                'encoding': 'ros1msg'
            }]
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1
        assert topics[0]['type'] == 'image'

    def test_get_image_topics_with_ros2_cdr(self, mock_mcap_reader):
        """识别 ROS2 CDR Image topic"""
        reader = mock_mcap_reader(
            channels=[{
                'id': 1,
                'topic': '/camera/image',
                'schema_id': 1,
                'message_encoding': 'cdr'
            }],
            schemas=[{
                'id': 1,
                'name': 'sensor_msgs/msg/Image',
                'encoding': 'ros2msg'
            }]
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1

    def test_get_image_topics_filters_non_image(self, mock_mcap_reader):
        """过滤非图像 topic"""
        reader = mock_mcap_reader(
            channels=[
                {'id': 1, 'topic': '/camera/image', 'schema_id': 1},
                {'id': 2, 'topic': '/odom', 'schema_id': 2},
                {'id': 3, 'topic': '/imu', 'schema_id': 3},
            ],
            schemas=[
                {'id': 1, 'name': 'sensor_msgs/msg/Image'},
                {'id': 2, 'name': 'nav_msgs/msg/Odometry'},
                {'id': 3, 'name': 'sensor_msgs/msg/Imu'},
            ]
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert len(topics) == 1
        assert topics[0]['name'] == '/camera/image'

    def test_get_image_topics_empty_mcap(self, mock_mcap_reader):
        """空 MCAP 文件返回空列表"""
        reader = mock_mcap_reader(channels=[], schemas=[])

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        topics = extractor.get_image_topics()
        assert topics == []


class TestGetTimeRange:
    """测试时间范围获取"""

    def test_get_time_range_success(self, mock_mcap_reader):
        """成功获取时间范围"""
        reader = mock_mcap_reader(
            statistics={
                'message_start_time': 1000000000,
                'message_end_time': 2000000000
            }
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        time_range = extractor.get_time_range()
        assert time_range == (1000000000, 2000000000)

    def test_get_time_range_no_statistics(self, mock_mcap_reader):
        """无统计信息返回 None"""
        reader = mock_mcap_reader(statistics=None)

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        time_range = extractor.get_time_range()
        assert time_range is None


class TestExtractFrame:
    """测试帧提取核心逻辑"""

    def test_extract_frame_ros1_compressed(self, mock_mcap_reader, sample_jpeg):
        """提取 ROS1 CompressedImage 帧"""
        # Mock ROS1 序列化的 CompressedImage 消息
        ros1_bytes = b'...'  # 模拟 ros1 序列化数据

        reader = mock_mcap_reader(
            channels=[{
                'id': 1,
                'topic': '/camera/compressed',
                'schema_id': 1,
                'message_encoding': 'ros1'
            }],
            schemas=[{
                'id': 1,
                'name': 'sensor_msgs/msg/CompressedImage',
                'encoding': 'ros1msg'
            }],
            messages=[
                {
                    'log_time': 1500000000,
                    'data': ros1_bytes
                }
            ]
        )

        # Mock typestore.deserialize_ros1 返回解码后的消息
        mock_decoded = MagicMock()
        mock_decoded.data = sample_jpeg

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_ros1.return_value = mock_decoded

        result = extractor.extract_frame('/camera/compressed', 1500000000)

        assert result is not None
        assert result.data == sample_jpeg
        assert result.timestamp_ns == 1500000000
        extractor._typestore.deserialize_ros1.assert_called_once()

    def test_extract_frame_ros2_cdr(self, mock_mcap_reader, sample_jpeg):
        """提取 ROS2 CDR Image 帧"""
        cdr_bytes = b'...'  # 模拟 CDR 序列化数据

        reader = mock_mcap_reader(
            channels=[{
                'id': 1,
                'topic': '/camera/image',
                'schema_id': 1,
                'message_encoding': 'cdr'
            }],
            schemas=[{
                'id': 1,
                'name': 'sensor_msgs/msg/Image',
                'encoding': 'ros2msg'
            }],
            messages=[{'log_time': 1000000000, 'data': cdr_bytes}]
        )

        mock_decoded = MagicMock()
        mock_decoded.height = 480
        mock_decoded.width = 640
        mock_decoded.encoding = 'bgr8'
        mock_decoded.data = np.zeros((480, 640, 3), dtype=np.uint8).tobytes()

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader
        extractor._typestore = MagicMock()
        extractor._typestore.deserialize_cdr.return_value = mock_decoded

        with patch('cv2.imencode', return_value=(True, np.array([1, 2, 3]))):
            result = extractor.extract_frame('/camera/image', 1000000000)

        assert result is not None
        extractor._typestore.deserialize_cdr.assert_called_once()

    def test_extract_frame_timestamp_clamping(self, mock_mcap_reader):
        """时间戳自动限制在有效范围内"""
        reader = mock_mcap_reader(
            statistics={
                'message_start_time': 1000000000,
                'message_end_time': 2000000000
            }
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        # 测试小于 start_time 的时间戳
        with patch.object(extractor, 'get_time_range', return_value=(1000000000, 2000000000)):
            # 验证内部逻辑会调整时间戳
            pass  # 具体实现测试

    def test_extract_frame_no_messages(self, mock_mcap_reader):
        """无消息时返回 None"""
        reader = mock_mcap_reader(messages=[])

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        result = extractor.extract_frame('/camera/image', 1000000000)
        assert result is None

    def test_extract_frame_unknown_topic(self, mock_mcap_reader):
        """未知 topic 返回 None"""
        reader = mock_mcap_reader(
            channels=[],
            schemas=[]
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        result = extractor.extract_frame('/unknown/topic', 1000000000)
        assert result is None

    def test_extract_frame_unknown_encoding(self, mock_mcap_reader):
        """未知 message_encoding 跳过并记录警告"""
        reader = mock_mcap_reader(
            channels=[{
                'id': 1,
                'topic': '/camera/image',
                'schema_id': 1,
                'message_encoding': 'protobuf'  # 未知编码
            }],
            schemas=[{'id': 1, 'name': 'sensor_msgs/msg/Image'}],
            messages=[{'log_time': 1000000000, 'data': b'data'}]
        )

        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._reader = reader

        with patch('app.services.frame_extractor.logger') as mock_logger:
            result = extractor.extract_frame('/camera/image', 1000000000)
            mock_logger.warning.assert_called_with(
                "Unknown message encoding: {}", "protobuf"
            )


class TestDecodeCompressedImage:
    """测试 CompressedImage 解码"""

    def test_decode_bytes_data(self, sample_jpeg):
        """处理 bytes 类型数据"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = sample_jpeg

        result = extractor._decode_compressed_image(msg)
        assert result == sample_jpeg

    def test_decode_numpy_array(self, sample_jpeg):
        """处理 numpy array 数据"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = np.frombuffer(sample_jpeg, dtype=np.uint8)

        result = extractor._decode_compressed_image(msg)
        assert result == sample_jpeg

    def test_decode_list_data(self):
        """处理 list 类型数据"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = [1, 2, 3, 4, 5]

        result = extractor._decode_compressed_image(msg)
        assert result == bytes([1, 2, 3, 4, 5])

    def test_decode_missing_data_attr(self):
        """缺失 data 属性返回 None"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        del msg.data  # 确保没有 data 属性

        result = extractor._decode_compressed_image(msg)
        assert result is None

    def test_decode_exception_handling(self):
        """异常处理返回 None 并记录日志"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.data = MagicMock()
        msg.data.tobytes.side_effect = Exception("Conversion error")

        with patch('app.services.frame_extractor.logger') as mock_logger:
            result = extractor._decode_compressed_image(msg)
            assert result is None
            mock_logger.warning.assert_called_once()


class TestDecodeRawImage:
    """测试原始 Image 解码"""

    def test_decode_rgb8(self):
        """解码 rgb8 编码"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = 'rgb8'
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8).tobytes()

        with patch('cv2.cvtColor') as mock_cvt, \
             patch('cv2.imencode', return_value=(True, np.array([1, 2, 3]))) as mock_encode:
            result = extractor._decode_raw_image(msg)
            mock_cvt.assert_called_once()  # RGB -> BGR 转换
            assert result is not None

    def test_decode_bgr8(self):
        """解码 bgr8 编码（无需颜色空间转换）"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = 'bgr8'
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8).tobytes()

        with patch('cv2.cvtColor') as mock_cvt, \
             patch('cv2.imencode', return_value=(True, np.array([1, 2, 3]))):
            result = extractor._decode_raw_image(msg)
            mock_cvt.assert_not_called()  # 不需要转换
            assert result is not None

    def test_decode_mono8(self):
        """解码 mono8 灰度编码"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = 'mono8'
        msg.data = np.zeros((2, 2), dtype=np.uint8).tobytes()

        with patch('cv2.imencode', return_value=(True, np.array([1, 2, 3]))):
            result = extractor._decode_raw_image(msg)
            assert result is not None

    def test_decode_unsupported_encoding(self):
        """不支持的编码返回 None 并记录警告"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = '16UC1'  # 不支持的编码
        msg.data = b'...'

        with patch('app.services.frame_extractor.logger') as mock_logger:
            result = extractor._decode_raw_image(msg)
            assert result is None
            mock_logger.warning.assert_called_with(
                "Unsupported image encoding: {}", "16UC1"
            )

    def test_decode_numpy_array_data(self):
        """处理 numpy array 类型的 data"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        msg = MagicMock()
        msg.height = 2
        msg.width = 2
        msg.encoding = 'rgb8'
        msg.data = np.zeros((2, 2, 3), dtype=np.uint8)  # numpy array, not bytes

        with patch('cv2.imencode', return_value=(True, np.array([1, 2, 3]))):
            result = extractor._decode_raw_image(msg)
            assert result is not None


class TestContextManager:
    """测试上下文管理器"""

    def test_context_manager_closes_file(self):
        """退出上下文时关闭文件句柄"""
        mock_file = MagicMock()

        with patch('builtins.open', return_value=mock_file):
            with McapFrameExtractor("/tmp/test.mcap") as extractor:
                extractor._file_handle = mock_file
                extractor._reader = MagicMock()

            mock_file.close.assert_called_once()

    def test_explicit_close(self):
        """显式调用 close 方法"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        mock_file = MagicMock()
        extractor._file_handle = mock_file
        extractor._reader = MagicMock()

        extractor.close()

        mock_file.close.assert_called_once()
        assert extractor._file_handle is None
        assert extractor._reader is None

    def test_close_with_no_file_handle(self):
        """无文件句柄时 close 不报错"""
        extractor = McapFrameExtractor("/tmp/test.mcap")
        extractor._file_handle = None

        extractor.close()  # 不应抛出异常
```

### 2.2 Frame API Endpoint 单元测试
**文件**: `services/dataset-service/tests/test_frame_api.py`

```python
"""Tests for Frame extraction API endpoint."""

class TestGetFrameEndpoint:
    """测试 GET /episodes/{id}/frame 端点"""

    def test_get_frame_success(self, client, auth_headers, mock_db, tmp_path):
        """成功获取帧"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        # Mock storage and extractor
        with patch('app.routers.episodes.StorageClient') as mock_storage, \
             patch('app.routers.episodes.McapFrameExtractor') as mock_extractor:

            mock_storage.return_value.download_to_file = AsyncMock()

            mock_frame = MagicMock()
            mock_frame.data = b'jpeg_data'
            mock_frame.timestamp_ns = 1000000000
            mock_frame.format = 'jpeg'

            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.extract_frame.return_value = mock_frame

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera/image&timestamp=1000000000",
                headers=auth_headers
            )

            assert resp.status_code == 200
            assert resp.content == b'jpeg_data'
            assert resp.headers['content-type'] == 'image/jpeg'
            assert resp.headers['x-frame-timestamp'] == '1000000000'
            assert 'cache-control' in resp.headers

    def test_get_frame_episode_not_found(self, client, auth_headers, mock_db):
        """Episode 不存在返回 404"""
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 404

    def test_get_frame_wrong_format(self, client, auth_headers, mock_db):
        """非 MCAP 格式返回 400"""
        ep = make_episode(fmt="hdf5")

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "only MCAP format supported" in resp.json()["detail"].lower()

    def test_get_frame_no_storage_path(self, client, auth_headers, mock_db):
        """无 storage_path 返回 400"""
        ep = make_episode(fmt="mcap")
        ep.storage_path = None

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "file not available" in resp.json()["detail"].lower()

    def test_get_frame_not_ready(self, client, auth_headers, mock_db):
        """Episode 状态非 ready 仍可获取帧（验证行为）"""
        ep = make_episode(fmt="mcap", status="processing")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        # 目前实现允许非 ready 状态获取帧，测试记录此行为
        with patch('app.routers.episodes.StorageClient'):
            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )
            # 如果实现改为拒绝非 ready 状态，这里应返回 400
            # 当前实现会继续处理

    def test_get_frame_no_frame_found(self, client, auth_headers, mock_db):
        """未找到帧返回 404"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch('app.routers.episodes.StorageClient') as mock_storage, \
             patch('app.routers.episodes.McapFrameExtractor') as mock_extractor:

            mock_storage.return_value.download_to_file = AsyncMock()
            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.extract_frame.return_value = None

            resp = client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=9999999999",
                headers=auth_headers
            )

            assert resp.status_code == 404
            assert "no frame found" in resp.json()["detail"].lower()

    def test_get_frame_missing_topic_param(self, client, auth_headers):
        """缺少 topic 参数返回 422"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 422

    def test_get_frame_missing_timestamp_param(self, client, auth_headers):
        """缺少 timestamp 参数返回 422"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera",
            headers=auth_headers
        )
        assert resp.status_code == 422

    def test_get_frame_invalid_timestamp(self, client, auth_headers):
        """无效 timestamp 返回 422"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera&timestamp=abc",
            headers=auth_headers
        )
        assert resp.status_code == 422

    def test_get_frame_unauthorized(self, client):
        """未认证返回 401"""
        resp = client.get(
            "/api/v1/episodes/00000000-0000-0000-0000-000000000000/frame?topic=/camera&timestamp=0"
        )
        assert resp.status_code in (401, 403)

    def test_get_frame_wrong_project(self, client, auth_headers, mock_db):
        """其他项目的 Episode 返回 404"""
        ep = make_episode(project_id=str(uuid.uuid4()))

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(
            f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
            headers=auth_headers
        )
        assert resp.status_code == 404

    def test_get_frame_cleans_up_temp_file(self, client, auth_headers, mock_db, tmp_path):
        """清理临时文件"""
        ep = make_episode(fmt="mcap", status="ready")
        ep.storage_path = "s3://bucket/test.mcap"

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        with patch('app.routers.episodes.StorageClient') as mock_storage, \
             patch('app.routers.episodes.McapFrameExtractor') as mock_extractor, \
             patch('os.unlink') as mock_unlink:

            mock_storage.return_value.download_to_file = AsyncMock()
            mock_extractor.return_value.__enter__ = MagicMock(return_value=mock_extractor.return_value)
            mock_extractor.return_value.__exit__ = MagicMock(return_value=False)
            mock_extractor.return_value.extract_frame.return_value = MagicMock(
                data=b'jpeg', timestamp_ns=0, format='jpeg'
            )

            client.get(
                f"/api/v1/episodes/{ep.id}/frame?topic=/camera&timestamp=0",
                headers=auth_headers
            )

            mock_unlink.assert_called_once()
```

## 3. 后端集成测试

### 3.1 使用真实 MCAP 文件测试
**文件**: `services/dataset-service/tests/integration/test_frame_extractor_integration.py`

```python
"""Integration tests for frame extractor using real MCAP files."""

import tempfile
import pytest

# 测试数据目录
TEST_DATA_DIR = Path(__file__).parent / "testdata"


class TestFrameExtractorWithRealRos1Mcap:
    """使用真实 ROS1 MCAP 文件测试"""

    @pytest.fixture(scope="class")
    def ros1_mcap_path(self):
        """提供 ROS1 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros1_compressed_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_read_ros1_compressed_image_topics(self, ros1_mcap_path):
        """读取 ROS1 CompressedImage topics"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()

            assert len(topics) > 0
            compressed_topics = [t for t in topics if t['type'] == 'compressed_image']
            assert len(compressed_topics) > 0

            for topic in topics:
                assert 'name' in topic
                assert 'type' in topic
                assert 'schema_name' in topic
                assert topic['schema_name'] in [
                    'sensor_msgs/msg/Image',
                    'sensor_msgs/msg/CompressedImage'
                ]

    def test_get_time_range_from_ros1_mcap(self, ros1_mcap_path):
        """获取 ROS1 MCAP 时间范围"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            time_range = extractor.get_time_range()

            assert time_range is not None
            start, end = time_range
            assert start < end
            assert start > 0  # ROS1 使用 Unix 时间戳

    def test_extract_frame_from_ros1_compressed(self, ros1_mcap_path):
        """从 ROS1 CompressedImage topic 提取帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            compressed_topics = [t for t in topics if t['type'] == 'compressed_image']

            if not compressed_topics:
                pytest.skip("No compressed image topics in test file")

            topic_name = compressed_topics[0]['name']
            time_range = extractor.get_time_range()
            mid_time = (time_range[0] + time_range[1]) // 2

            frame = extractor.extract_frame(topic_name, mid_time)

            assert frame is not None
            assert isinstance(frame.data, bytes)
            assert len(frame.data) > 0
            assert frame.timestamp_ns >= time_range[0]
            assert frame.timestamp_ns <= time_range[1]

            # 验证是有效的 JPEG
            assert frame.data[:2] == b'\xff\xd8'  # JPEG SOI marker
            assert frame.data[-2:] == b'\xff\xd9'  # JPEG EOI marker

    def test_extract_frame_timestamp_clamping(self, ros1_mcap_path):
        """时间戳自动调整到有效范围"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]['name']
            time_range = extractor.get_time_range()

            # 请求范围外的时间戳
            frame = extractor.extract_frame(topic_name, 0)
            assert frame is not None
            assert frame.timestamp_ns >= time_range[0]

    def test_extract_frame_closest_timestamp(self, ros1_mcap_path):
        """提取最接近目标时间戳的帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]['name']
            time_range = extractor.get_time_range()

            # 在不同时间点提取帧
            frame1 = extractor.extract_frame(topic_name, time_range[0])
            frame2 = extractor.extract_frame(topic_name, time_range[1])

            assert frame1 is not None
            assert frame2 is not None
            assert frame1.timestamp_ns != frame2.timestamp_ns


class TestFrameExtractorWithRealRos2Mcap:
    """使用真实 ROS2 MCAP 文件测试"""

    @pytest.fixture(scope="class")
    def ros2_mcap_path(self):
        """提供 ROS2 MCAP 测试文件路径"""
        path = TEST_DATA_DIR / "ros2_images.mcap"
        if not path.exists():
            pytest.skip(f"Test data not found: {path}")
        return path

    def test_read_ros2_image_topics(self, ros2_mcap_path):
        """读取 ROS2 Image topics"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros2_mcap_path) as extractor:
            topics = extractor.get_image_topics()

            assert len(topics) > 0
            for topic in topics:
                assert topic['schema_name'] in [
                    'sensor_msgs/msg/Image',
                    'sensor_msgs/msg/CompressedImage'
                ]

    def test_extract_frame_from_ros2_raw_image(self, ros2_mcap_path):
        """从 ROS2 raw Image topic 提取并编码帧"""
        from app.services.frame_extractor import McapFrameExtractor

        with McapFrameExtractor(ros2_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            raw_topics = [t for t in topics if t['type'] == 'image']

            if not raw_topics:
                pytest.skip("No raw image topics in test file")

            topic_name = raw_topics[0]['name']
            time_range = extractor.get_time_range()
            mid_time = (time_range[0] + time_range[1]) // 2

            frame = extractor.extract_frame(topic_name, mid_time)

            assert frame is not None
            assert isinstance(frame.data, bytes)
            assert len(frame.data) > 0
            # 验证是有效的 JPEG
            assert frame.data[:2] == b'\xff\xd8'


class TestFrameExtractorConcurrency:
    """并发安全测试"""

    def test_multiple_extractors_same_file(self, ros1_mcap_path):
        """多个 extractor 同时读取同一文件"""
        from app.services.frame_extractor import McapFrameExtractor
        import concurrent.futures

        def extract_frame(extractor, topic, timestamp):
            return extractor.extract_frame(topic, timestamp)

        with McapFrameExtractor(ros1_mcap_path) as extractor:
            topics = extractor.get_image_topics()
            if not topics:
                pytest.skip("No image topics")

            topic_name = topics[0]['name']
            time_range = extractor.get_time_range()

            # 并发提取
            timestamps = [
                time_range[0] + i * (time_range[1] - time_range[0]) // 10
                for i in range(5)
            ]

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(extract_frame, extractor, topic_name, ts)
                    for ts in timestamps
                ]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            assert all(r is not None for r in results)
```

## 4. E2E 测试

### 4.1 MCAP 预览完整流程测试
**文件**: `tests/e2e/test_mcap_preview.py`

```python
"""E2E tests for MCAP preview functionality.

Covers: upload MCAP -> ingest -> preview -> frame extraction.
"""

import pytest
import asyncio
from pathlib import Path

from .helpers import E2EClient, wait_for_episode_status


@pytest.mark.e2e
class TestMcapPreviewWorkflow:
    """MCAP 预览完整工作流"""

    @pytest.fixture
    def sample_mcap_path(self):
        """提供测试用 MCAP 文件"""
        path = Path(__file__).parent / "fixtures" / "sample_ros1.mcap"
        if not path.exists():
            pytest.skip(f"Test fixture not found: {path}")
        return path

    async def test_upload_and_preview_mcap(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """上传 MCAP 并验证预览功能"""
        # 1. 上传文件
        with open(sample_mcap_path, "rb") as f:
            data = f.read()

        size_bytes = len(data)
        filename = sample_mcap_path.name

        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": filename, "size_bytes": size_bytes, "format": "mcap"}
        )
        assert init_resp.status_code == 200, f"Upload init failed: {init_resp.text}"

        session_id = init_resp.json()["session_id"]
        episode_id = init_resp.json()["episode_id"]
        chunk_size = init_resp.json()["chunk_size"]
        total_chunks = init_resp.json()["total_chunks"]

        # 2. 上传分片
        for i in range(total_chunks):
            start = i * chunk_size
            chunk = data[start:start + chunk_size]
            chunk_resp = await gateway_client.dataset.put(
                f"/api/v1/episodes/upload/{session_id}/chunk/{i}",
                content=chunk,
                headers={"Content-Type": "application/octet-stream"}
            )
            assert chunk_resp.status_code == 200, f"Chunk {i} upload failed"

        # 3. 完成上传
        complete_resp = await gateway_client.dataset.post(
            f"/api/v1/episodes/upload/{session_id}/complete"
        )
        assert complete_resp.status_code == 200

        # 4. 等待处理完成
        episode = await wait_for_episode_status(
            gateway_client, episode_id, "ready", timeout=60
        )
        assert episode["format"] == "mcap"

        # 5. 获取 episode 详情（包含 topics）
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        assert detail_resp.status_code == 200

        detail = detail_resp.json()
        assert "topics" in detail

        # 6. 过滤图像 topics
        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage"
            ]
        ]

        if not image_topics:
            pytest.skip("No image topics in uploaded MCAP")

        # 7. 请求帧提取
        topic_name = image_topics[0]["name"]
        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)
        mid_timestamp = duration_ns // 2

        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": topic_name, "timestamp": mid_timestamp}
        )
        assert frame_resp.status_code == 200, f"Frame extraction failed: {frame_resp.text}"

        # 8. 验证响应
        assert frame_resp.headers["content-type"] == "image/jpeg"
        assert "x-frame-timestamp" in frame_resp.headers
        assert len(frame_resp.content) > 0

        # 9. 验证是有效的 JPEG
        assert frame_resp.content[:2] == b'\xff\xd8'  # JPEG SOI
        assert frame_resp.content[-2:] == b'\xff\xd9'  # JPEG EOI

    async def test_preview_non_mcap_returns_error(
        self, gateway_client: E2EClient
    ):
        """预览非 MCAP 文件返回错误"""
        # 创建 HDF5 episode
        init_resp = await gateway_client.dataset.post(
            "/api/v1/episodes/upload/init",
            json={"filename": "test.hdf5", "size_bytes": 1024, "format": "hdf5"}
        )
        assert init_resp.status_code == 200

        # ... 上传和完成流程

        # 尝试获取帧应返回 400
        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": "/camera", "timestamp": 0}
        )
        assert frame_resp.status_code == 400

    async def test_preview_frame_not_found(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """请求不存在的时间戳返回 404"""
        # 上传并等待就绪
        # ...

        # 请求超出范围的时间戳
        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": "/nonexistent/topic", "timestamp": 9999999999999}
        )
        assert frame_resp.status_code == 404

    async def test_preview_multiple_topics(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """并发请求多个 topic 的帧"""
        # 上传并等待就绪
        # ...

        # 获取所有图像 topics
        detail_resp = await gateway_client.dataset.get(f"/api/v1/episodes/{episode_id}")
        detail = detail_resp.json()

        image_topics = [
            t for t in detail["topics"]
            if t.get("schema_name") in [
                "sensor_msgs/msg/Image",
                "sensor_msgs/msg/CompressedImage"
            ]
        ]

        if len(image_topics) < 2:
            pytest.skip("Need at least 2 image topics")

        # 并发请求多个 topic
        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)
        timestamp = duration_ns // 2

        async def fetch_frame(topic):
            return await gateway_client.dataset.get(
                f"/api/v1/episodes/{episode_id}/frame",
                params={"topic": topic["name"], "timestamp": timestamp}
            )

        responses = await asyncio.gather(*[
            fetch_frame(topic) for topic in image_topics[:3]
        ])

        for resp in responses:
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"


@pytest.mark.e2e
class TestMcapPreviewPerformance:
    """MCAP 预览性能测试"""

    async def test_frame_extraction_response_time(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """帧提取响应时间 < 1s"""
        # 上传并等待就绪
        # ...

        import time

        start = time.time()
        frame_resp = await gateway_client.dataset.get(
            f"/api/v1/episodes/{episode_id}/frame",
            params={"topic": topic_name, "timestamp": timestamp}
        )
        elapsed = time.time() - start

        assert frame_resp.status_code == 200
        assert elapsed < 1.0, f"Frame extraction took {elapsed}s, expected < 1s"

    async def test_sequential_frame_requests(
        self, gateway_client: E2EClient, sample_mcap_path: Path
    ):
        """顺序请求多个帧"""
        # 上传并等待就绪
        # ...

        duration_ns = int(detail["duration_seconds"] * 1_000_000_000)
        timestamps = [duration_ns * i // 10 for i in range(10)]

        for ts in timestamps:
            resp = await gateway_client.dataset.get(
                f"/api/v1/episodes/{episode_id}/frame",
                params={"topic": topic_name, "timestamp": ts}
            )
            assert resp.status_code == 200
```

## 5. 前端测试

### 5.1 useMcapFrames Hook 测试
**文件**: `web/src/hooks/__tests__/useMcapFrames.test.ts`

```typescript
import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useMcapFrames } from "../useMcapFrames";
import * as episodesApi from "@/api/episodes";

// Mock API
vi.mock("@/api/episodes");

describe("useMcapFrames", () => {
  const mockGetFrame = vi.mocked(episodesApi.getFrame);

  beforeEach(() => {
    vi.clearAllMocks();
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("initialization", () => {
    it("should initialize with empty frames and not loading", () => {
      const { result } = renderHook(() =>
        useMcapFrames({ episodeId: "test-episode", topics: [] })
      );

      expect(result.current.frames.size).toBe(0);
      expect(result.current.isLoading).toBe(false);
    });

    it("should initialize with empty frames when topics provided", () => {
      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      expect(result.current.frames.size).toBe(0);
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe("loadFrames", () => {
    it("should load frames for all topics", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      expect(result.current.frames.size).toBe(2);
      expect(result.current.frames.get("/camera/image1")).toBe("blob:test-1");
      expect(result.current.frames.get("/camera/image2")).toBe("blob:test-1");
      expect(mockGetFrame).toHaveBeenCalledTimes(2);
    });

    it("should use cache for previously loaded frames", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // First load
      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Second load with same timestamp (100ms bucket)
      await act(async () => {
        await result.current.loadFrames(1000050000);
      });

      expect(mockGetFrame).toHaveBeenCalledTimes(1);
    });

    it("should handle API errors gracefully", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      mockGetFrame
        .mockResolvedValueOnce({ blobUrl: "blob:test-1", timestampNs: 1000 })
        .mockRejectedValueOnce(new Error("Network error"));

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1", "/camera/image2"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Should have one frame, one failed
      expect(result.current.frames.size).toBe(1);
      expect(result.current.frames.get("/camera/image1")).toBe("blob:test-1");
      expect(result.current.frames.has("/camera/image2")).toBe(false);

      consoleSpy.mockRestore();
    });

    it("should set loading state during request", async () => {
      let resolveFrame: (value: any) => void;
      const framePromise = new Promise((resolve) => {
        resolveFrame = resolve;
      });
      mockGetFrame.mockReturnValue(framePromise);

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      act(() => {
        result.current.loadFrames(1000000000);
      });

      expect(result.current.isLoading).toBe(true);

      await act(async () => {
        resolveFrame!({ blobUrl: "blob:test", timestampNs: 1000 });
        await framePromise;
      });

      expect(result.current.isLoading).toBe(false);
    });

    it("should cancel pending requests on new load", async () => {
      const abortSpy = vi.spyOn(AbortController.prototype, "abort");
      mockGetFrame.mockImplementation(() => new Promise(() => {})); // Never resolve

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      act(() => {
        result.current.loadFrames(1000000000);
      });

      act(() => {
        result.current.loadFrames(2000000000);
      });

      expect(abortSpy).toHaveBeenCalled();
    });

    it("should do nothing when topics array is empty", async () => {
      const { result } = renderHook(() =>
        useMcapFrames({ episodeId: "test-episode", topics: [] })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      expect(mockGetFrame).not.toHaveBeenCalled();
    });
  });

  describe("preloadFrames", () => {
    it("should preload frames without updating state", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:preloaded",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      await act(async () => {
        await result.current.preloadFrames(1000000000);
      });

      expect(mockGetFrame).toHaveBeenCalled();
      expect(result.current.frames.size).toBe(0); // State not updated
    });

    it("should ignore preload errors", async () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      mockGetFrame.mockRejectedValue(new Error("Network error"));

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // Should not throw
      await act(async () => {
        await result.current.preloadFrames(1000000000);
      });

      consoleSpy.mockRestore();
    });

    it("should skip already cached topics", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test",
        timestampNs: 1000000000,
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      // Load first
      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      // Preload same timestamp
      await act(async () => {
        await result.current.preloadFrames(1000000000);
      });

      expect(mockGetFrame).toHaveBeenCalledTimes(1);
    });
  });

  describe("cleanup", () => {
    it("should revoke blob URLs on unmount", async () => {
      mockGetFrame.mockResolvedValue({
        blobUrl: "blob:test-1",
        timestampNs: 1000000000,
      });

      const { result, unmount } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: ["/camera/image1"],
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      unmount();

      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-1");
    });
  });

  describe("concurrency", () => {
    it("should limit concurrent requests to MAX_CONCURRENT", async () => {
      let activeRequests = 0;
      let maxActiveRequests = 0;

      mockGetFrame.mockImplementation(async () => {
        activeRequests++;
        maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
        await new Promise((resolve) => setTimeout(resolve, 10));
        activeRequests--;
        return { blobUrl: "blob:test", timestampNs: 1000 };
      });

      const { result } = renderHook(() =>
        useMcapFrames({
          episodeId: "test-episode",
          topics: Array(10).fill("/camera/image").map((t, i) => `${t}${i}`),
        })
      );

      await act(async () => {
        await result.current.loadFrames(1000000000);
      });

      expect(maxActiveRequests).toBeLessThanOrEqual(3);
    });
  });
});
```

### 5.2 VideoGrid 组件测试
**文件**: `web/src/components/__tests__/VideoGrid.test.tsx`

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { VideoGrid } from "../VideoGrid";

describe("VideoGrid", () => {
  describe("empty state", () => {
    it("should show empty message when no topics", () => {
      render(<VideoGrid topics={[]} frames={new Map()} isLoading={false} />);

      expect(screen.getByText("No image topics found in this episode")).toBeInTheDocument();
    });
  });

  describe("grid layout", () => {
    it("should render single column for 1 topic", () => {
      const { container } = render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(1, minmax(0, 1fr))");
    });

    it("should render 2 columns for 2 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={["/camera/image1", "/camera/image2"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(2, minmax(0, 1fr))");
    });

    it("should render 2 columns for 4 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(4).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(2, minmax(0, 1fr))");
    });

    it("should render 3 columns for 6 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(6).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(3, minmax(0, 1fr))");
    });

    it("should render 4 columns for 10 topics", () => {
      const { container } = render(
        <VideoGrid
          topics={Array(10).fill("/camera/image").map((t, i) => `${t}${i}`)}
          frames={new Map()}
          isLoading={false}
        />
      );

      const grid = container.querySelector("[style*='grid-template-columns']");
      expect(grid).toHaveStyle("grid-template-columns: repeat(4, minmax(0, 1fr))");
    });
  });

  describe("frame display", () => {
    it("should show loading spinner when loading", () => {
      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={true}
        />
      );

      expect(screen.getByRole("status")).toBeInTheDocument(); // Spinner
    });

    it("should show 'No frame' when not loading and no frame", () => {
      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      expect(screen.getByText("No frame")).toBeInTheDocument();
    });

    it("should display frame image when available", () => {
      const frames = new Map([["/camera/image", "blob:test-frame"]]);

      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={frames}
          isLoading={false}
        />
      );

      const img = screen.getByAltText("/camera/image");
      expect(img).toHaveAttribute("src", "blob:test-frame");
    });

    it("should display topic name overlay", () => {
      render(
        <VideoGrid
          topics={["/camera/image"]}
          frames={new Map()}
          isLoading={false}
        />
      );

      expect(screen.getByText("/camera/image")).toBeInTheDocument();
    });

    it("should handle multiple topics with mixed frame states", () => {
      const frames = new Map([
        ["/camera/image1", "blob:frame1"],
        // /camera/image2 has no frame
      ]);

      render(
        <VideoGrid
          topics={["/camera/image1", "/camera/image2"]}
          frames={frames}
          isLoading={false}
        />
      );

      expect(screen.getByAltText("/camera/image1")).toHaveAttribute("src", "blob:frame1");
      expect(screen.getAllByText("No frame").length).toBe(1);
    });
  });

  describe("topic rendering", () => {
    it("should render all topics with unique keys", () => {
      const topics = ["/camera/left", "/camera/right", "/depth/image"];

      const { container } = render(
        <VideoGrid
          topics={topics}
          frames={new Map()}
          isLoading={false}
        />
      );

      topics.forEach((topic) => {
        expect(screen.getByText(topic)).toBeInTheDocument();
      });
    });

    it("should truncate long topic names", () => {
      const longTopic = "/very/long/topic/name/that/should/be/truncated";

      render(
        <VideoGrid
          topics={[longTopic]}
          frames={new Map()}
          isLoading={false}
        />
      );

      const topicElement = screen.getByText(longTopic);
      expect(topicElement).toHaveClass("truncate");
    });
  });
});
```

### 5.3 TimelineControl 组件测试
**文件**: `web/src/components/__tests__/TimelineControl.test.tsx`

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TimelineControl } from "../TimelineControl";

describe("TimelineControl", () => {
  const defaultProps = {
    currentTime: 5000000000, // 5s in ns
    duration: 60, // 60s
    isPlaying: false,
    playbackRate: 1,
    onSeek: vi.fn(),
    onPlay: vi.fn(),
    onPause: vi.fn(),
    onRateChange: vi.fn(),
  };

  describe("time display", () => {
    it("should display current time", () => {
      render(<TimelineControl {...defaultProps} />);

      expect(screen.getByText("00:05.000")).toBeInTheDocument();
    });

    it("should display total duration", () => {
      render(<TimelineControl {...defaultProps} />);

      expect(screen.getByText("01:00.000")).toBeInTheDocument();
    });

    it("should format times correctly", () => {
      const { rerender } = render(
        <TimelineControl {...defaultProps} currentTime={12500000000} duration={125} />
      );

      expect(screen.getByText("00:12.500")).toBeInTheDocument();
      expect(screen.getByText("02:05.000")).toBeInTheDocument();
    });
  });

  describe("progress bar", () => {
    it("should show correct progress", () => {
      const { container } = render(<TimelineControl {...defaultProps} />);

      const slider = container.querySelector('input[type="range"]');
      expect(slider).toHaveValue("8.33"); // 5/60 * 100
    });

    it("should handle zero duration", () => {
      const { container } = render(
        <TimelineControl {...defaultProps} duration={0} />
      );

      const slider = container.querySelector('input[type="range"]');
      expect(slider).toHaveValue("0");
    });

    it("should call onSeek when slider changes", () => {
      const onSeek = vi.fn();
      const { container } = render(
        <TimelineControl {...defaultProps} onSeek={onSeek} />
      );

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.change(slider, { target: { value: "50" } });

      expect(onSeek).toHaveBeenCalledWith(30000000000); // 50% of 60s in ns
    });
  });

  describe("play/pause controls", () => {
    it("should show Play button when paused", () => {
      render(<TimelineControl {...defaultProps} isPlaying={false} />);

      expect(screen.getByText("▶ Play")).toBeInTheDocument();
    });

    it("should show Pause button when playing", () => {
      render(<TimelineControl {...defaultProps} isPlaying={true} />);

      expect(screen.getByText("⏸ Pause")).toBeInTheDocument();
    });

    it("should call onPlay when Play clicked", () => {
      const onPlay = vi.fn();
      render(<TimelineControl {...defaultProps} onPlay={onPlay} isPlaying={false} />);

      fireEvent.click(screen.getByText("▶ Play"));

      expect(onPlay).toHaveBeenCalled();
    });

    it("should call onPause when Pause clicked", () => {
      const onPause = vi.fn();
      render(<TimelineControl {...defaultProps} onPause={onPause} isPlaying={true} />);

      fireEvent.click(screen.getByText("⏸ Pause"));

      expect(onPause).toHaveBeenCalled();
    });
  });

  describe("skip buttons", () => {
    it("should skip backward 5s", () => {
      const onSeek = vi.fn();
      render(<TimelineControl {...defaultProps} onSeek={onSeek} />);

      fireEvent.click(screen.getByTitle("Back 5s"));

      expect(onSeek).toHaveBeenCalledWith(0); // 5s - 5s = 0
    });

    it("should skip forward 5s", () => {
      const onSeek = vi.fn();
      render(<TimelineControl {...defaultProps} onSeek={onSeek} />);

      fireEvent.click(screen.getByTitle("Forward 5s"));

      expect(onSeek).toHaveBeenCalledWith(10000000000); // 5s + 5s = 10s in ns
    });

    it("should clamp to 0 when skipping backward past start", () => {
      const onSeek = vi.fn();
      render(
        <TimelineControl {...defaultProps} onSeek={onSeek} currentTime={2000000000} />
      );

      fireEvent.click(screen.getByTitle("Back 5s"));

      expect(onSeek).toHaveBeenCalledWith(0);
    });

    it("should clamp to duration when skipping forward past end", () => {
      const onSeek = vi.fn();
      render(
        <TimelineControl {...defaultProps} onSeek={onSeek} currentTime={58000000000} />
      );

      fireEvent.click(screen.getByTitle("Forward 5s"));

      expect(onSeek).toHaveBeenCalledWith(60000000000); // clamped to 60s
    });
  });

  describe("playback rate", () => {
    it("should display all rate options", () => {
      render(<TimelineControl {...defaultProps} />);

      expect(screen.getByText("0.5x")).toBeInTheDocument();
      expect(screen.getByText("1x")).toBeInTheDocument();
      expect(screen.getByText("2x")).toBeInTheDocument();
    });

    it("should highlight current rate", () => {
      const { container } = render(
        <TimelineControl {...defaultProps} playbackRate={2} />
      );

      const rateButton = screen.getByText("2x");
      expect(rateButton).toHaveClass("bg-blue-600");
    });

    it("should call onRateChange when rate clicked", () => {
      const onRateChange = vi.fn();
      render(<TimelineControl {...defaultProps} onRateChange={onRateChange} />);

      fireEvent.click(screen.getByText("0.5x"));

      expect(onRateChange).toHaveBeenCalledWith(0.5);
    });
  });

  describe("dragging indicator", () => {
    it("should show time tooltip when dragging", () => {
      const { container } = render(<TimelineControl {...defaultProps} />);

      const slider = container.querySelector('input[type="range"]')!;
      fireEvent.mouseDown(slider);

      expect(screen.getByText("00:05.000")).toBeInTheDocument();
    });
  });
});
```

### 5.4 PreviewPage 集成测试
**文件**: `web/src/pages/__tests__/PreviewPage.test.tsx`

```typescript
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PreviewPage } from "../PreviewPage";

// Mock dependencies
vi.mock("@/api/episodes");
vi.mock("@/hooks/useMcapFrames");

describe("PreviewPage", () => {
  const createTestQueryClient = () =>
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

  const renderWithProviders = (ui: React.ReactElement, episodeId = "test-id") => {
    const queryClient = createTestQueryClient();
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/preview/${episodeId}`]}>
          <Routes>
            <Route path="/preview/:episodeId" element={ui} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("loading states", () => {
    it("should show spinner while loading episode", () => {
      // Mock loading state
      vi.mocked(useEpisode).mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  describe("error states", () => {
    it("should show not found when episode does not exist", () => {
      vi.mocked(useEpisode).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Episode not found")).toBeInTheDocument();
    });
  });

  describe("format validation", () => {
    it("should show error for non-MCAP files", () => {
      vi.mocked(useEpisode).mockReturnValue({
        data: { format: "hdf5", filename: "test.hdf5" },
        isLoading: false,
      } as any);

      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("Preview is only available for MCAP files")).toBeInTheDocument();
    });
  });

  describe("playback controls", () => {
    beforeEach(() => {
      vi.mocked(useEpisode).mockReturnValue({
        data: {
          id: "test-id",
          format: "mcap",
          filename: "test.mcap",
          duration_seconds: 60,
          topics: [
            { name: "/camera/image", schema_name: "sensor_msgs/msg/Image" },
          ],
        },
        isLoading: false,
      } as any);

      vi.mocked(useMcapFrames).mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames: vi.fn(),
        preloadFrames: vi.fn(),
      });
    });

    it("should display episode filename in header", () => {
      renderWithProviders(<PreviewPage />);

      expect(screen.getByText("test.mcap")).toBeInTheDocument();
    });

    it("should load initial frames on mount", () => {
      const loadFrames = vi.fn();
      vi.mocked(useMcapFrames).mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames,
        preloadFrames: vi.fn(),
      });

      renderWithProviders(<PreviewPage />);

      expect(loadFrames).toHaveBeenCalledWith(0);
    });

    it("should handle play/pause toggle", () => {
      renderWithProviders(<PreviewPage />);

      const playButton = screen.getByText("▶ Play");
      fireEvent.click(playButton);

      expect(screen.getByText("⏸ Pause")).toBeInTheDocument();
    });

    it("should handle seeking", () => {
      const loadFrames = vi.fn();
      vi.mocked(useMcapFrames).mockReturnValue({
        frames: new Map(),
        isLoading: false,
        loadFrames,
        preloadFrames: vi.fn(),
      });

      renderWithProviders(<PreviewPage />);

      // Simulate seek
      // ...
    });
  });

  describe("topic filtering", () => {
    it("should filter only image topics", () => {
      vi.mocked(useEpisode).mockReturnValue({
        data: {
          format: "mcap",
          duration_seconds: 60,
          topics: [
            { name: "/camera/image", schema_name: "sensor_msgs/msg/Image" },
            { name: "/odom", schema_name: "nav_msgs/Odometry" },
            { name: "/imu", schema_name: "sensor_msgs/Imu" },
          ],
        },
        isLoading: false,
      } as any);

      renderWithProviders(<PreviewPage />);

      // Only image topics should be passed to useMcapFrames
      // Verify through mock calls
    });
  });
});
```

## 6. 测试执行策略

```bash
# 1. 后端单元测试
cd services/dataset-service
pytest tests/test_frame_extractor.py -v
pytest tests/test_frame_api.py -v

# 2. 后端集成测试（需要真实 MCAP 文件）
pytest tests/integration/test_frame_extractor_integration.py -v

# 3. E2E 测试
cd /home/xuhao/embedai
make e2e-module MODULE=mcap_preview

# 4. 前端单元测试
cd web
npm test -- --coverage

# 5. 全量测试
make test  # 运行所有测试
```

## 7. 测试数据准备

```
testdata/
├── ros1_compressed_images.mcap    # ROS1 CompressedImage 测试文件
├── ros1_raw_images.mcap           # ROS1 raw Image 测试文件
├── ros2_images.mcap               # ROS2 Image 测试文件
├── ros2_compressed.mcap           # ROS2 CompressedImage 测试文件
├── empty.mcap                     # 空 MCAP 文件
├── no_images.mcap                 # 无图像 topic 的 MCAP
└── corrupt.mcap                   # 损坏的 MCAP 文件
```

## 8. 覆盖率目标

| 层级 | 目标覆盖率 | 关键路径 |
|------|-----------|---------|
| 单元测试 | >80% | frame_extractor.py 所有解码路径 |
| 集成测试 | >60% | 真实 MCAP 文件处理 |
| E2E 测试 | 核心流程 | 上传->提取帧->预览完整流程 |
| 前端测试 | >70% | useMcapFrames, VideoGrid, TimelineControl |
