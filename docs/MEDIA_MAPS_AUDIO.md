# Nâng cấp nội dung, media, bản đồ và nhạc

Bản nâng cấp giữ Flask, HTML/CSS/JavaScript, avatar và dữ liệu đang dùng. Không cần chuyển framework hoặc mua thêm dịch vụ để bật các chức năng cơ bản. Mã được sửa tại máy phát triển, chưa tự push hoặc Reload tài khoản PythonAnywhere.

## Chức năng

- Nội dung nhật ký và thư có khung nền sáng, viền, bo góc, padding; giữ xuống dòng và xuống dòng được cả chuỗi dài. Dữ liệu vẫn dùng `textContent`, không chèn HTML do người dùng nhập.
- Chỉ tên tác giả trong `.journal-post-meta` dùng nhãn `.journal-post-author`; ngày và ID giữ mức nhấn nhẹ hơn.
- `#secret-recipient` là trường có sẵn, tự chọn người còn lại theo ID `tuan`/`thu`, khi mở, đổi người viết và reset form. Trường người nhận chỉ đọc; backend từ chối gửi cho chính mình. Đổi tên trong Cài đặt không thay quan hệ ID.
- Bấm địa điểm mở bảng chọn Google Maps hoặc Apple Maps, không tự chuyển đi. Liên kết sử dụng vĩ độ/kinh độ GPS đã lưu, kể cả `0,0`; nhãn địa điểm không thay đổi ghim. Bài chỉ có tên nhập tay vẫn đọc bình thường và được giải thích khi chưa có tọa độ.
- Giữ một audio `#love-audio`, nguồn nhạc hiện tại và nút phát đĩa. Thanh tùy chỉnh có tua bằng chuột/chạm/phím, thời gian, tổng thời lượng và tắt tiếng. Trạng thái lấy từ audio thật; thời lượng chưa có không hiển thị phần trăm giả. Khi JavaScript không chạy, trình điều khiển audio gốc vẫn có mặt.

## Ảnh/video và giới hạn thực tế

Luồng mới nhận JPEG, PNG, WebP, MP4 và WebM trong cả nhật ký lẫn thư. Có thể chọn nhiều đợt, xem trước, gỡ từng tệp và theo dõi tiến trình từng tệp. Ứng dụng không còn giới hạn 5 tệp, 5 MB/tệp hay quota ảnh nhật ký 128 MiB. Biến cũ `LOVEDAYS_JOURNAL_MAX_BYTES` không còn áp đặt quota.

Hàng đợi tải tối đa hai tệp đồng thời để giữ ứng dụng ổn định; đây không phải giới hạn số tệp được đính kèm. Mỗi tệp được gửi theo phần 1 MiB, đọc/ghi theo khối nhỏ. Tệp lớn không được chuyển toàn bộ thành Base64 hoặc đọc toàn bộ video vào RAM. Giới hạn 1 MiB là kích thước một request truyền tải, không phải kích thước cả tệp.

Backend lưu tiến trình, offset và quyền sở hữu upload trong SQLite; tệp nằm ngoài Git. Khi mạng lỗi, bấm **Thử lại tệp** để lấy offset từ máy chủ và tiếp tục. Khởi động lại worker không xóa các phần đã commit. Tệp đã tải xong được giữ nếu lưu bài lỗi; sửa nội dung/mật khẩu rồi gửi lại sẽ dùng lại ID tệp đã hoàn tất. Phiên xác thực hết hạn vẫn phải mở khóa lại trước khi tiếp tục; upload nền không tự gia hạn hòm thư.

Bản nháp và đối tượng File của trình duyệt hiện giữ trong RAM của tab. Đóng hoặc tải lại tab khi chưa lưu sẽ mất bản nháp và hàng đợi phía trình duyệt; việc tiếp tục tải được kiểm tra cho lỗi mạng và restart worker trong khi tab còn mở. Tệp đã gắn vào bài/thư tồn tại bền vững sau Reload và đọc được từ thiết bị khác theo quyền hiện có.

Upload chưa gắn vào bài không tự hết hạn, để có thể thử lại sau lỗi. Khi cần giải phóng các tệp bị bỏ dở, kiểm tra trước trong Bash, dùng đúng kho và virtualenv:

```bash
export LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE
python server.py cleanup-uploads --older-than-days 7 --dry-run
```

Bỏ `--dry-run` chỉ khi muốn dọn thật các upload chưa dùng cũ hơn số ngày đã chọn. CLI bảo vệ tệp đang được thư, nhật ký hoặc lịch sử tham chiếu, kể cả sau một lần commit bị gián đoạn. Đây là bước quản trị thủ công, không phải giới hạn số lượng hoặc dung lượng đính kèm.

Ảnh mới giữ nguyên byte gốc; ảnh cũ không bị viết lại. Video được kiểm tra cấu trúc container MP4/WebM và kiểu MIME thực tế, không chỉ đuôi tệp; không giải mã/transcode toàn bộ video. Codec bên trong còn phụ thuộc trình duyệt. Video dùng `controls`, `playsinline`, `preload="none"`, không tự phát hàng loạt. Khi không phát được, có liên kết tải video gốc. Backend hỗ trợ HTTP Range để phát/tua tệp. Các endpoint kiểm tra phiên và quyền lịch sử trước khi phục vụ media.

[PythonAnywhere Free](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/) hiện có tổng **512 MiB** cho mã, môi trường Python, database, ảnh/video và file sao lưu; một web worker. Vì vậy bỏ giới hạn nghiệp vụ không tạo ra dung lượng lưu trữ vô hạn. Khi filesystem báo hết chỗ/quota, API trả lỗi 507 rõ ràng và giữ các phần đã hoàn tất. Cần giải phóng file không dùng, dọn upload bỏ dở, hoặc chuyển sang hạ tầng/kho lưu trữ có dung lượng phù hợp nếu vượt khả năng tài khoản. Bản này dùng kho riêng PythonAnywhere, chưa tích hợp object storage ngoài.

Không coi giới hạn upload 100 MiB ở giao diện **Files** của PythonAnywhere là giới hạn của API website. Luồng chia phần tránh gửi cả video trong một request dài. PythonAnywhere vẫn có timeout worker và giới hạn tài khoản; thời gian kiểm tra/lưu media cực lớn còn phụ thuộc CPU, I/O và quota thực tế. Xem [tài liệu timeout](https://help.pythonanywhere.com/pages/ErrorReloadingWebApp/).

## Lưu trữ và migration

Kho cũ `<DATA_DIR>` tiếp tục dùng chung cho WSGI và CLI:

```text
<DATA_DIR>/
  auth.sqlite3
  letters.json
  images/
  journal-images/
  media/
  media-incoming/
  secret.key
  admin-encryption.key
  admin-lookup.key
```

Ảnh cũ vẫn ở thư mục cũ. `images[]` trong JSON/API giữ tên để tương thích dữ liệu hiện có và có thể chứa cả video. Metadata mới bổ sung `kind: image|video`, `mimeType`, `storageArea`, `storageKey`, `originalName`, `size`, `order` và UUID. API công khai loại bỏ đường dẫn lưu nội bộ. Không đặt các thư mục trên vào static mappings.

Migration thêm bảng upload, cache/rate địa điểm và phiên bản tính năng 2; không làm rỗng JSON hoặc viết lại ảnh cũ. Bài nhật ký, media được nhận vào bài và lịch sử dùng cùng giao dịch. Thư JSON được ghi thay thế an toàn; backend nhận biết tham chiếu JSON sau crash để không cho hàng đợi xóa hoặc tái sử dụng tệp đã gắn vào thư.

Sao lưu toàn bộ kho bằng `scripts/backup_private.py` như [hướng dẫn nâng cấp](UPGRADE_SETTINGS_JOURNAL.md). Tạm ngừng upload trong lúc sao lưu; bản sao giữ khóa JSON và SQLite để chụp file/media cùng metadata nhất quán. Backup lớn có thể khiến upload chờ khóa rồi phải thử lại, dữ liệu đã commit được giữ.

## Geoapify và địa chỉ

Chỉ khi bấm **Lấy vị trí hiện tại**, trình duyệt mới xin quyền GPS, rồi gọi `/api/location/reverse`. API key nằm ở backend. Tọa độ gốc, độ chính xác GPS, địa chỉ tra cứu và nhãn người dùng được lưu riêng:

```json
{
  "label": "Tên địa điểm do người dùng kiểm tra",
  "latitude": 18.3551234567,
  "longitude": 105.887654321,
  "accuracy": 12.5,
  "lookupAddress": "Địa chỉ do dịch vụ trả về",
  "lookupDistanceMeters": 6.2,
  "source": "geoapify",
  "approximate": false,
  "attribution": "Powered by Geoapify · © OpenStreetMap contributors",
  "attributionUrl": "https://www.geoapify.com/"
}
```

Kết quả gần nhất trong 10 m được ưu tiên, kể cả khoảng cách 0; nếu không có thì nhận địa chỉ phù hợp đến 100 m. API reverse không có tham số bán kính nên backend đánh giá khoảng cách trong kết quả. Xa hơn chỉ lấy nhãn khu vực gần đúng, có thông báo; không gán tên cửa hàng lân cận thành địa chỉ chính xác. `accuracy` là độ chính xác GPS, khác khoảng cách tới địa chỉ tra cứu. Kết quả API chậm không ghi đè tên đã sửa thủ công hoặc lần lấy vị trí mới hơn.

Biến môi trường mới duy nhất cần cung cấp để bật dịch vụ:

```text
LOVEDAYS_GEOAPIFY_API_KEY
```

Không có key hoặc API lỗi, trang vẫn giữ tọa độ và cho nhập tay. Timeout mặc định 5 giây, cache riêng trong SQLite 24 giờ, rate limit 12 yêu cầu/phút theo trình duyệt và IP. Không ghi URL chứa key vào log. Tham số kỹ thuật có thể đổi trong cấu hình Flask `GEOCODE_TIMEOUT_SECONDS`, `GEOCODE_CACHE_SECONDS`, `GEOCODE_REQUESTS_PER_MINUTE`.

Geoapify cho dùng gói miễn phí trong production theo quota và yêu cầu ghi nguồn. Theo [bảng giá chính thức](https://www.geoapify.com/pricing/), gói Free hiện có 3.000 credits/ngày, tối đa 5 request/giây; không cần thẻ. Giữ các liên kết Geoapify và OpenStreetMap bên cạnh thông tin địa điểm. [Tài liệu reverse API](https://apidocs.geoapify.com/docs/geocoding/reverse-geocoding/) và [điều kiện ghi nguồn](https://www.geoapify.com/terms-and-conditions/).

## Cập nhật PythonAnywhere

1. Trong PowerShell máy phát triển, commit/push cả các module mới. Thư mục runtime, API key, database và ảnh riêng không đưa vào Git:

```powershell
Set-Location "C:\Users\Admin\Downloads\lovedays-main"
git status --short
git add server.py site_features.py media_uploads.py location_service.py index.html main docs tests
git diff --cached --stat
git commit -m "Add resumable media, maps, geocoding and audio controls"
git push origin main
```

2. Sao lưu toàn bộ kho trước khi pull theo hướng dẫn đã có. Nếu đang upload, chờ hoặc tạm dừng trước khi sao lưu.
3. Trong Bash của PythonAnywhere chạy:

```bash
cd /home/USERNAME/love
source /home/USERNAME/.virtualenvs/lovedays/bin/activate
git pull --ff-only origin main
python -m pip install --no-cache-dir -r requirements.txt
export LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE
python server.py migrate
```

Không có dependency Python mới; Pillow, Flask và các thư viện sẵn có tiếp tục được dùng. Không cần ffmpeg/ffprobe để chạy luồng upload hiện tại. Không chạy lại khởi tạo mật khẩu hoặc reset tài khoản.

Thay `USERNAME` bằng tên tài khoản PythonAnywhere của bạn; nếu đã đặt `LOVEDAYS_DATA_DIR` riêng, giữ cùng giá trị khi chạy CLI và WSGI.

4. Nếu muốn tra cứu địa chỉ, đăng ký tại [Geoapify MyProjects](https://myprojects.geoapify.com/), tạo project rồi lấy API key. Trong WSGI configuration của PythonAnywhere, đặt biến trước dòng import ứng dụng:

```python
import os
os.environ["LOVEDAYS_GEOAPIFY_API_KEY"] = "YOUR_SERVER_API_KEY"

from pythonanywhere_wsgi import application
```

Đây là phần bổ sung vào WSGI đang dùng dưới `/var/www/`; giữ nguyên đường dẫn project, `LOVEDAYS_DATA_DIR`, origin, Secure cookie và SQLite DELETE. Thay placeholder bằng key thật chỉ trong cấu hình riêng trên máy chủ, không trong repo, HTML hoặc JavaScript. Khi chạy CLI kiểm tra dịch vụ phải cung cấp cùng biến môi trường; biến export ở Bash không tự truyền sang Web app.

`api.geoapify.com` hiện có trong [allowlist của PythonAnywhere Free](https://www.pythonanywhere.com/whitelist/). `urllib` dùng cấu hình proxy môi trường của PythonAnywhere; nếu hosting trả 403, kiểm tra allowlist/proxy theo [hướng dẫn chính thức](https://help.pythonanywhere.com/pages/403ForbiddenError/). Không bỏ kiểm tra TLS để xử lý lỗi kết nối.

5. Giữ hai static mapping `/main/` và `/fonts/`; không map `/api`, `media`, `media-incoming` hoặc kho riêng. Vào **Web → Reload**, chờ xong rồi tải lại website/Ctrl+F5.
6. Kiểm tra: thư cũ, bài cũ, đổi người gửi hai chiều, phát/tua nhạc, đăng ảnh/video, retry sau lỗi mạng, sửa bài với mật khẩu, và lấy vị trí trên HTTPS. Thiếu key không ngăn đăng bài.

Liên kết bản đồ theo [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started) và [Apple Unified Map URLs](https://developer.apple.com/documentation/mapkit/unified-map-urls). Có liên kết Apple tương thích kiểu cũ trong bảng chọn. Việc ứng dụng native có mở hay chỉ hiện web phụ thuộc thiết bị, cài đặt và phiên bản trình duyệt; chưa kiểm tra trên điện thoại thật.

## Kiểm chứng

Xem [TEST_REPORT.md](TEST_REPORT.md) cho các nhóm và kết quả đã chạy. Test dùng kho, mật khẩu và tệp tổng hợp riêng; không truy cập thư thật hoặc tài khoản production. Video VP8 tổng hợp nhỏ phát thật trong Chrome, ảnh gốc trên 5 MiB được so byte, và upload gián đoạn được thử lại từ offset đã lưu. Geoapify được mock để kiểm tra khoảng cách, lỗi và phản hồi chậm; chưa có API key thật để kiểm tra dịch vụ live. Chưa chạy Safari/iOS, Android vật lý hoặc deploy/reload trên tài khoản PythonAnywhere thay người dùng.
