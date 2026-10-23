# Nâng cấp nhật ký, quản trị và tự khóa trên PythonAnywhere

Thực hiện theo thứ tự sao lưu → cập nhật mã → cài dependency → migrate/setup → Reload → kiểm tra. Hướng dẫn dùng Bash của PythonAnywhere, virtualenv `lovedays` và repository tại `~/love`. Mã được sửa tại máy phát triển; chưa tự push hoặc thay website online.

## Dữ liệu và quyền

- Thư bí mật vẫn ở `letters.json` UTF-8 và `images/`, không di chuyển hay ghi đè thư cũ.
- `auth.sqlite3` được mở rộng bằng migration lặp an toàn: phiên hòm thư, tài khoản quản trị, cài đặt, bài nhật ký, metadata ảnh và lịch sử. Nhật ký/hồ sơ/cài đặt không dùng localStorage làm kho chính.
- Nhật ký đã đăng và ảnh của bài đang hiển thị là công khai. Đăng mới cần phiên hòm thư hoặc phiên quản trị; có thể soạn trước rồi mở khóa khi gửi. Nội dung cần riêng tư tiếp tục dùng hòm thư.
- Mỗi lần sửa/xóa bài phải nhập mật khẩu nhật ký, kể cả quản trị viên. Khi chưa đặt mật khẩu này, các thao tác sửa/xóa bị chặn. Lịch sử cần quản trị hoặc quyền được mở bằng mật khẩu nhật ký, có hiệu lực 5 phút.
- Mật khẩu hòm thư chung không phải tài khoản quản trị. Hai quản trị viên có cùng quyền; người gửi/người nhận thư và tên tác giả bài không tạo danh tính đăng nhập.

## 1. Đưa mã mới lên GitHub

Từ PowerShell trên máy phát triển, sau khi rà soát thay đổi:

```powershell
Set-Location "C:\Users\Admin\Downloads\lovedays-main"
git status --short
git add server.py site_features.py requirements.txt index.html main README.md docs scripts/backup_private.py tests
git diff --cached --stat
git commit -m "Add journal, encrypted admin settings and mailbox expiry"
git push origin main
```

Không stage kho runtime, file khóa mã hóa, `.env`, database, ảnh riêng hoặc ZIP sao lưu. Nếu đã commit thì chỉ cần push commit còn thiếu. Không force push để bỏ qua xung đột.

## 2. Sao lưu trước khi pull trên PythonAnywhere

Tạm ngưng thao tác đăng/sửa/xóa từ các thiết bị trong lúc sao lưu và nâng cấp. Mở Consoles → Bash:

```bash
cd ~/love
source ~/.virtualenvs/lovedays/bin/activate
export LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE
python -c "from server import create_app; print(create_app().config['DATA_DIR'])"
```

Ghi lại đường dẫn kho được in. Để chạy công cụ sao lưu trước khi thay mã đang triển khai, lấy riêng script từ commit vừa push vào thư mục công cụ ngoài repo:

```bash
mkdir -p ~/lovedays-upgrade-tools/scripts
curl -fL https://raw.githubusercontent.com/leanhtuan19/love/main/scripts/backup_private.py -o ~/lovedays-upgrade-tools/scripts/backup_private.py
task_data_dir=$(python -c "from server import create_app; print(create_app().config['DATA_DIR'])")
python ~/lovedays-upgrade-tools/scripts/backup_private.py --data-dir "$task_data_dir" --repository "$PWD"
```

Chỉ tiếp tục khi lệnh thành công và in đường dẫn ZIP. `--repository "$PWD"` nhận diện checkout thật khi helper nằm ở thư mục công cụ, để chặn đặt bản sao bên trong mã nguồn. Script không import/migrate app khi sao lưu; nó khóa JSON và giữ quyền ghi SQLite để chụp bản nhất quán bằng SQLite Backup API, kèm toàn bộ ảnh/khóa, không chép thô một SQLite đang ghi. File ZIP mặc định ở `~/lovedays-backups/`, quyền riêng, ngoài repo và static mappings.

Tải ZIP về qua tab Files và kiểm tra danh sách file trong archive trước khi tiếp tục. ZIP chứa dữ liệu xác thực và khóa: không đưa lên GitHub, thư mục public hoặc chia sẻ công khai. Để đủ quota miễn phí, cần chỗ trống cho bản sao; không xóa dữ liệu đang dùng để lấy chỗ. Thư mục snapshot SQLite tạm được dọn tự động.

## 3. Pull, cài thư viện và migration

```bash
cd ~/love
git pull --ff-only origin main
source ~/.virtualenvs/lovedays/bin/activate
python -m pip install --no-cache-dir -r requirements.txt
export LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE
python server.py migrate
```

Dependency mới là `cryptography` để mã hóa username. Giữ phiên bản Python của Web app trùng virtualenv. Nếu pip lỗi, dừng và đọc lỗi cài đặt trước khi Reload; không bỏ qua kiểm tra chứng chỉ TLS.

Migration cũng chạy khi tạo app, có thể chạy lại an toàn. Nó bổ sung cột/bảng còn thiếu và dùng dữ liệu HTML/hồ sơ hiện có làm mặc định lần đầu; không nạp dữ liệu mẫu, không làm rỗng JSON và không đặt lại các nhóm cài đặt đã lưu. Khóa file JSON tiếp tục tạo riêng theo PID để tương thích worker fork của PythonAnywhere.

## 4. Setup hai quản trị viên lần đầu

```bash
python server.py setup-admins
```

Nhập lần lượt hai bộ thông tin quản trị bạn đã chọn. Dùng chính thông tin trong yêu cầu ban đầu nếu muốn giữ tài khoản đã yêu cầu; không suy ra tên/ngày sinh từ mật khẩu. Username thứ hai có dấu gạch dưới ở cuối nếu đó là tên bạn chọn, không có dấu gạch chéo ngược. Mật khẩu cần 8–256 ký tự, nhập xác nhận hai lần; ký tự mật khẩu không hiện khi gõ.

CLI hỗ trợ biến môi trường cho triển khai tự động, nhưng không cần chúng khi nhập tương tác:

| Biến | Mục đích |
| --- | --- |
| `LOVEDAYS_ADMIN_1_USERNAME` | Username quản trị viên thứ nhất |
| `LOVEDAYS_ADMIN_1_PASSWORD` | Mật khẩu khởi tạo tài khoản thứ nhất |
| `LOVEDAYS_ADMIN_2_USERNAME` | Username quản trị viên thứ hai |
| `LOVEDAYS_ADMIN_2_PASSWORD` | Mật khẩu khởi tạo tài khoản thứ hai |

Không lưu các giá trị thật trong repo hay lệnh có thể vào shell history. Cơ chế setup kiểm tra dưới transaction: nếu đã có tài khoản, chạy lại sẽ giữ nguyên. Sau khi đổi username/mật khẩu trong Cài đặt, dữ liệu ban đầu không được giữ làm tài khoản dự phòng. Không có thông tin đăng nhập mặc định trong frontend hoặc API công khai.

## 5. Khóa riêng, môi trường và static mappings

Kho runtime hiện có thêm:

```text
<DATA_DIR>/
  letters.json
  images/
  auth.sqlite3
  secret.key
  admin-encryption.key
  admin-lookup.key
  journal-images/
```

`admin-encryption.key` dùng cho Fernet (mã hóa có xác thực); `admin-lookup.key` là khóa HMAC chỉ mục username. Hai khóa nằm ngoài database và source. Nếu database đã có tài khoản mà khóa bị mất, ứng dụng dừng thay vì sinh khóa thay thế làm mất khả năng giải mã. Sao lưu và phục hồi cả kho với bộ khóa tương ứng. Trên Linux dùng thư mục 0700 và các file khóa/database riêng 0600; tài khoản chạy app phải đọc/ghi/tạo/đổi tên trong kho.

WSGI tiếp tục import `application` từ `pythonanywhere_wsgi`. Giữ `LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE` cho cả Web app và CLI trên PythonAnywhere. Nếu dùng `LOVEDAYS_DATA_DIR` tùy chỉnh, phải đặt cùng đường dẫn ở WSGI và Bash; export trong Bash không tự truyền sang worker.

| Cấu hình | Giá trị/ý nghĩa |
| --- | --- |
| `LOVEDAYS_COOKIE_SECURE` | `true` trên HTTPS; adapter đã đặt mặc định |
| `LOVEDAYS_PUBLIC_ORIGIN` | Origin HTTPS thật, không có `/api` hoặc `/love`; adapter suy ra miền US, EU cần đặt đúng miền |
| `LOVEDAYS_JOURNAL_MAX_BYTES` | Mặc định 134217728, tức 128 MiB tổng ảnh nhật ký, gồm ảnh lịch sử |
| `LOVEDAYS_PASSWORD_HASH` | Nếu từng đặt override, gỡ nó trước khi đổi mật khẩu hòm thư trong Cài đặt |

Đổi các biến của Web app bằng cấu hình WSGI/môi trường riêng trên máy chủ trước import, rồi Reload. Không sửa khóa hạ tầng qua trang Cài đặt. Các giới hạn nghiệp vụ có thể sửa trong Cài đặt được lưu ở SQLite.

Static mappings giữ đúng:

| URL | Directory |
| --- | --- |
| `/main/` | `/home/USERNAME/love/main` |
| `/fonts/` | `/home/USERNAME/love/fonts` |

Không ánh xạ toàn repo, `/api`, kho riêng hoặc `journal-images`. Ảnh nhật ký được backend kiểm tra bài/quyền lịch sử rồi mới phục vụ. Avatar gốc được giữ nguyên cho đến khi bạn chủ động đổi URL trong Cài đặt. Nhạc dùng file trong `main/music`; hình ảnh công khai có thể dùng đường dẫn `main/img` hoặc URL HTTPS. Không cần dịch vụ reverse geocoding: nút vị trí lấy tọa độ, cho sửa nhãn địa điểm thủ công trước khi đăng.

## 6. Reload và cấu hình lần đầu trong giao diện

1. Vào Web → chọn đúng domain → Reload, chờ hoàn tất. Tải lại trình duyệt không thay thế bước này.
2. Mở website HTTPS, bấm bánh răng góc dưới phải và đăng nhập một quản trị viên đã setup.
3. Trong Bảo mật đặt mật khẩu sửa/xóa nhật ký và xác nhận. Mật khẩu mới không được hiển thị lại sau khi lưu.
4. Mặc định khóa hòm thư sau 300 giây không thao tác trong hòm thư; bấm đóng đặt hạn 30 giây. Mở lại không xóa hạn đóng. Các API kiểm tra mốc sớm nhất; vẫn có trần phiên tuyệt đối 30 phút từ cơ chế xác thực hiện có.
5. Trong Thông tin cá nhân/Nội dung website sửa và lưu từng nhóm; tên, hồ sơ, lời nhắn, bộ đếm ngày, hình ảnh và các nội dung công khai lấy dữ liệu máy chủ. Các nhãn vận hành như thông báo lỗi vẫn thuộc mã giao diện.
6. Khi đổi tài khoản, nhập lại mật khẩu của quản trị viên đang thao tác. Phiên của tài khoản được thay đổi bị thu hồi, không còn chấp nhận thông tin cũ.

## 7. Kiểm tra sau nâng cấp

- Mở khóa hộp thư, kiểm tra 5 phút không dùng; thao tác ở phần khác/ảnh nền/API nền không gia hạn. Đóng rồi mở trong 30 giây vẫn bị khóa khi đến hạn; thử ở hai tab và sau chuyển nền điện thoại.
- Nút ổ khóa khóa ngay, API đọc thư/ảnh riêng từ chối phiên cũ. Bản nháp chưa lưu được giữ trong RAM của tab trong lúc đang mở website, mất khi đóng/tải lại tab.
- Đăng nhật ký có ảnh, kiểm tra xuống dòng và ngày Việt Nam. Cho phép/từ chối quyền vị trí rồi nhập thủ công để xác nhận cả hai luồng.
- Tìm bằng ID, tên, tiêu đề/nội dung không dấu, ngày `dd/mm/yyyy` hoặc bộ lọc từ/đến. Thử nút tải thêm khi nhiều bài.
- Thử sai/đúng mật khẩu nhật ký khi sửa/xóa; sai không làm thay đổi bài/ảnh. Lịch sử ghi trước/sau và vẫn còn sau xóa mềm; ảnh đã gỡ/xóa không đọc công khai được nữa.
- Đăng nhập cả hai quản trị viên; sửa một nhóm cài đặt không ghi đè nhóm khác; đổi thông tin đăng nhập rồi chạy lại setup để xác nhận không phục hồi tài khoản cũ.
- Reload ứng dụng rồi kiểm tra thư, nhật ký, lịch sử, ảnh và cài đặt còn nguyên. Kiểm tra Error log chỉ với bản ghi mới sau lần Reload.

Ảnh nhận JPEG/PNG/WebP, tối đa 5 ảnh/bài, 5 MiB/ảnh, tối đa 12 triệu pixel và mỗi cạnh 8000 px. Máy chủ giải mã và tạo lại ảnh, không tin phần mở rộng. Ảnh cũ vẫn giữ để lịch sử xem được và tính vào quota; giới hạn 128 MiB không phải toàn bộ quota tài khoản PythonAnywhere. Theo dõi Files, tải bản sao lưu về máy, và gia hạn Web app hàng tháng theo [hướng dẫn miễn phí](DEPLOY_FREE.md).

## Kiểm chứng và giới hạn

Xem [TEST_REPORT.md](TEST_REPORT.md) cho các lệnh/kết quả thực tế. Kiểm thử dùng kho và credentials ngẫu nhiên; chưa tạo tài khoản thật hoặc deploy trên PythonAnywhere thay bạn. Chromium mobile mô phỏng và sự kiện chuyển nền mô phỏng không thay thế iPhone/Safari và Android vật lý.

Cơ chế mật khẩu dùng scrypt có salt theo khả năng tương thích hiện có; username dùng thư viện mã hóa có xác thực. Tham chiếu [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [Fernet](https://cryptography.io/en/latest/fernet/).
