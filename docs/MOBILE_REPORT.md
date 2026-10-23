# Báo cáo sửa giao diện mobile

Ngày kiểm tra: 23/10/2026. Mã nguồn vẫn dùng HTML/CSS/JavaScript và Flask hiện có. Không thay đổi avatar, dữ liệu, mật khẩu, API hay cấu trúc lưu trữ.

## Nguyên nhân đã xác định

- Đo trực tiếp trong Chromium có mô phỏng cảm ứng: ở 320 × 740 và 740 × 320, ô đăng nhập quản trị và các ô soạn nhật ký có `font-size` thực tế **14px**. Đây là điều kiện thường khiến Safari iOS tự phóng to ô đang nhập; môi trường kiểm tra không có iPhone để tái hiện hành vi Safari thật. Ô mật khẩu hòm thư đã là 16px khi có con trỏ cảm ứng, nhưng quy tắc riêng và các biểu mẫu mới chưa được áp dụng đồng bộ.
- Modal nhật ký/hồ sơ dùng `svh` hoặc chiều cao viewport bố cục; khi bàn phím chỉ thu hẹp vùng nhìn trực quan, khung có thể lớn hơn phần màn hình còn lại. Các popup chưa dùng chung chiều cao và độ lệch của `VisualViewport`.
- Mỗi nhóm popup tự quản lý khóa cuộn. Chồng popup xem ảnh hoặc mở/đóng liên tiếp dễ làm các nhóm khôi phục trạng thái cuộn khác nhau. Một số nút đóng định vị tuyệt đối có thể cuộn khỏi vùng nhìn.
- Một số grid/flex và ô ngày, tên dài, đường dẫn không có khoảng trắng chưa co và xuống dòng đồng bộ. Danh sách thư trên mobile dùng cuộn ngang; đã đổi sang danh sách dọc để đọc và thao tác không cần kéo ngang. Khi cưỡng bức zoom 2 lần qua Chrome DevTools Protocol, đã phát hiện phong thư trang trí gây tràn nội bộ 10px trong popup rộng 179px; đổi phần giấy và dấu niêm phong theo tỉ lệ đã khắc phục trường hợp này.

Baseline không cho thấy trang mặc định tràn ngang ở hai kích thước đã đo: popup quản trị/nhật ký rộng 282px trên màn hình 320px; hòm thư rộng 292px. Việc sửa bố cục tập trung thêm các trường hợp nội dung dài, bàn phím, chữ lớn và popup lồng nhau.

## Các thay đổi chính

- `index.html`: một khai báo viewport duy nhất; tải `main/js/mobile.js` trước các mã popup. Viewport và điều khiển chạm hỗ trợ hạn chế zoom ngoài ý muốn trong khả năng của trình duyệt.
- `main/js/mobile.js`: quản lý khóa cuộn dùng chung theo từng popup; giữ vị trí trang và chỉ khôi phục sau khi popup cuối đóng. Đọc chiều rộng, chiều cao, `offsetTop` và `offsetLeft` từ `VisualViewport`, có phương án dùng viewport bố cục khi API không có. Cập nhật qua `requestAnimationFrame`; chỉ đưa ô đang nhập vào vùng nhìn sau khi resize/focus ổn định. Dọn listener và timer khi mở khóa cuối cùng.
- `main/js/letters.js`, `main/js/journal.js`, `main/js/profiles.js`: dùng chung cơ chế viewport/khóa cuộn; giữ focus và các luồng xác thực, soạn, ảnh, lưu hiện có.
- `main/css/style.css`, `main/css/letters.css`, `main/css/journal.css`: ô nhập tối thiểu 16px trên mobile/cảm ứng; grid/flex co được; chữ dài xuống dòng; popup theo vùng nhìn khả dụng và safe area; cuộn dọc nội bộ và giữ nút đóng tiếp cận được. Animation xuất hiện của chính khung popup dùng opacity để tránh transform ở phần tử cha làm ô nhập co lại hoặc lệch vị trí trong lúc mở. Không thu nhỏ toàn trang bằng `scale` hoặc `zoom` để sửa bố cục.
- `main/css/effects.css`: màn hình loading tính safe area, xuống dòng văn bản dài và cuộn được ở màn hình ngang thấp.
- `tests/test_mobile_layout.py`: kiểm thử trình duyệt thật chạy headless với dữ liệu và mật khẩu thử ngẫu nhiên, tách khỏi kho dữ liệu thật.

## Kiểm thử

Chạy:

```bash
python -m unittest discover -s tests -p test_mobile_layout.py -v
```

Ma trận Chromium mô phỏng cảm ứng gồm chiều rộng 320, 360, 375, 390, 414, 430, 768px; ngang 844 × 390 và 740 × 320; desktop 1280 × 900 dùng chuột. Các kiểm tra đo hình học và CSS thực tế sau khi trang tải:

- Chỉ có một viewport meta; không tràn ngang tài liệu hoặc nội dung popup; popup và nút đóng nằm trong vùng nhìn.
- Các ô tìm kiếm, ngày, mật khẩu, tên, textarea, select và upload đang hiển thị đạt tối thiểu 16px, không dùng transform thu nhỏ trường nhập.
- Tên/URL không có khoảng trắng, nhiều dòng tiếng Việt, 3 ảnh thật, trình xem ảnh lồng nhau, cuộn tới cuối nội dung vẫn đóng được popup.
- Giữ khóa cuộn nền khi chỉ đóng trình xem ảnh; khôi phục vị trí trang sau khi đóng popup cuối và qua ba chu kỳ mở/đóng.
- Mô phỏng `VisualViewport` đổi chiều cao, độ lệch và xoay thiết bị; chuyển ô nhập rồi đóng bàn phím; có phương án khi không có API này.
- Tăng 200% kích thước chữ đã đo trong cài đặt bằng stylesheet thử; kiểm tra biểu mẫu dài ở dọc, ngang và tablet.
- Dùng Chrome DevTools Protocol tăng page scale lên 2 lần cho nhật ký, lớp mật khẩu hòm thư và hồ sơ để kiểm tra popup vẫn thao tác được khi trình duyệt cho phép ghi đè hạn chế zoom, sau đó trả về 1 lần.

Kết quả: **7/7 bài mới đạt**. Các bài đã được chạy theo nhóm trong quá trình sửa; sau khi phát hiện và sửa tràn phong thư lúc zoom, đã chạy lại riêng bài zoom và ma trận responsive/animation vừa bổ sung. Ngoài bộ mới, **27/27 bài hồi quy có sẵn** về giao diện, hòm thư, nhật ký/quản trị, cử chỉ và build tĩnh đã đạt trong đợt sửa này. Không có lỗi JavaScript trong các luồng được kiểm tra.

## Phạm vi và giới hạn

- Trình duyệt thực đã chạy: Chromium/Chrome headless trên Windows, với viewport/cảm ứng mobile mô phỏng. Dữ liệu, upload, API và JavaScript ứng dụng chạy thật trong máy chủ Flask thử nghiệm.
- Chiều cao bàn phím, độ lệch `VisualViewport`, chữ lớn và thao tác zoom nêu trên là mô phỏng; không tương đương bàn phím hoặc tăng cỡ chữ trên thiết bị thật.
- Chưa kiểm tra Safari/Chrome iOS, Chrome/Samsung Internet/Firefox Android trên điện thoại thật; chưa có WebKit hoặc Firefox cục bộ trong môi trường này. Không khẳng định tương thích tuyệt đối các trình duyệt chưa kiểm tra.
- Safari/iOS và thiết lập trợ năng có thể bỏ qua hạn chế zoom. Bản sửa dựa trên kích thước chữ và bố cục trước; không chặn toàn bộ sự kiện chạm hoặc cuộn. Người dùng vẫn cần được cuộn dọc, chọn chữ và thao tác biểu mẫu.
- Có thể xuất hiện `ResourceWarning` của máy chủ thử Werkzeug khi trình duyệt hủy tải trước MP3; đây không phải lỗi JavaScript hoặc lỗi bố cục.

Trước khi phát hành rộng, nên kiểm tra chuỗi mở popup → chạm ô → bàn phím hiện → nhập dài → chuyển ô → đóng bàn phím → đóng/mở lại trên ít nhất một iPhone và một Android. Kiểm tra thêm xoay máy, tăng cỡ chữ hệ thống, pinch theo thiết lập trình duyệt và vị trí trang sau khi đóng popup.

## Cập nhật PythonAnywhere

Đây là thay đổi frontend; không cần khởi tạo lại tài khoản, đổi mật khẩu, xóa dữ liệu hoặc chạy migration mới. Commit/push các file đã sửa từ máy tính lên nhánh đang triển khai. Sau đó vào Bash PythonAnywhere:

```bash
cd /home/at19xyz/love
git pull --ff-only origin main
```

Vào **Web → Reload** cho `at19xyz.pythonanywhere.com`, rồi tải lại website bằng Ctrl + F5 hoặc làm mới cache trên điện thoại. Giữ nguyên WSGI, virtualenv, `LOVEDAYS_DATA_DIR` và hai static mapping `/main/`, `/fonts/` hiện có. File `mobile.js` mới được phục vụ qua `/main/`; không tạo mapping đến kho dữ liệu riêng.

Nếu `git pull` báo xung đột hoặc thay đổi local, kiểm tra `git status` và giữ lại thay đổi để xử lý; không chạy reset/xóa dữ liệu để bỏ qua lỗi. Nếu giao diện còn dùng mã cũ, kiểm tra Network đã tải `/main/js/mobile.js` thành công và đã Reload Web app.

Tham khảo: [VisualViewport](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport), [viewport meta và giới hạn zoom](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/meta/name/viewport), [touch-action](https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action).
