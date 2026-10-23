# Triển khai miễn phí: GitHub + PythonAnywhere Beginner

Phương án này chạy giao diện và API Flask hiện có trên cùng một địa chỉ HTTPS. Thư vẫn lưu JSON, ảnh nằm trong kho riêng và SQLite quản lý xác thực. Không cần đổi framework, tạo database trả phí hoặc đặt dữ liệu riêng trong GitHub.

Tài liệu này dùng hệ thống US tại www.pythonanywhere.com, gói Beginner $0/tháng. Đăng ký từ [trang Beginner](https://www.pythonanywhere.com/registration/register/beginner/), không chọn gói Developer. [Bảng giá chính thức](https://www.pythonanywhere.com/pricing/).

## 1. Những giới hạn cần biết

- Một web app, một worker, tổng dung lượng tài khoản 512 MiB; dung lượng gồm mã nguồn, môi trường Python, JSON, ảnh và các file khác.
- Web app có hạn một tháng. Vào tab Web và bấm gia hạn trước hạn hiển thị; đặt nhắc lịch mỗi tháng. Gia hạn này vẫn miễn phí.
- Dùng tên miền miễn phí `https://USERNAME.pythonanywhere.com`; HTTPS có sẵn. Tên miền riêng thuộc gói trả phí.
- Không có SSH bên ngoài; dùng Bash console và Files trong Dashboard. Các lệnh ở dưới chạy được trong trình duyệt.

[Giới hạn Free hiện hành](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/), [HTTPS mặc định](https://help.pythonanywhere.com/pages/HTTPSSetup/), [gia hạn ứng dụng — đọc cập nhật mới về thời hạn một tháng](https://blog.pythonanywhere.com/129/).

Đây là lựa chọn cho website cá nhân có ít người dùng. PythonAnywhere không khuyến nghị SQLite cho hệ thống production tải cao. Adapter dùng SQLite DELETE journal vì WAL không phù hợp với network filesystem; JSON và ảnh vẫn ở kho riêng. [PythonAnywhere và SQLite](https://help.pythonanywhere.com/pages/KindsOfDatabases/), [giới hạn SQLite WAL](https://www.sqlite.org/wal.html).

## 2. Push mã từ Windows lên GitHub

Mở PowerShell tại thư mục dự án:

```powershell
Set-Location "C:\Users\Admin\Downloads\lovedays-main"
git status --short
git add server.py pythonanywhere_wsgi.py docs/DEPLOY_FREE.md docs/DEPLOYMENT.md docs/BACKEND.md docs/TEST_REPORT.md tests/test_pythonanywhere.py README.md
git diff --cached --stat
git commit -m "Support free PythonAnywhere deployment"
git push origin main
```

Nếu còn thay đổi chức năng từ các lần sửa trước chưa được push, stage các file mã nguồn đó trước khi commit. Giữ kho dữ liệu thật, mật khẩu, `.env`, SQLite và khóa riêng ngoài Git. Trong GitHub cần có `pythonanywhere_wsgi.py`, `server.py`, `requirements.txt`, `index.html`, `main/` và `fonts/`.

Nếu Git báo không có thay đổi để commit vì bạn đã commit trước đó, chỉ cần push phần commit còn thiếu. Nếu push bị rejected, đồng bộ thay đổi trên remote và giải quyết xung đột; không dùng force push để bỏ qua.

## 3. Tạo tài khoản và chọn phiên bản Python

1. Đăng ký tài khoản Beginner ở liên kết đầu tài liệu và xác nhận email.
2. Ghi lại username PythonAnywhere; nó có thể khác username GitHub.
3. Trong Account → System Image kiểm tra phiên bản Python hiện có. Hướng dẫn dùng Python 3.12 trên image có hỗ trợ phiên bản này.
4. Nếu giao diện không có Python 3.12, có thể chọn Python 3.10 hoặc mới hơn, nhưng phải dùng đúng cùng phiên bản khi tạo virtualenv và Web app. Không dùng Python 2.

[Các Python version theo system image](https://help.pythonanywhere.com/pages/PythonVersions/).

## 4. Lấy mã và cài thư viện trên PythonAnywhere

Mở Consoles → Bash. Các lệnh trong phần này là Bash trên máy chủ, không phải PowerShell trên Windows:

```bash
git clone --depth 1 https://github.com/leanhtuan19/love.git ~/love
cd ~/love
python3.12 -m venv ~/.virtualenvs/lovedays
source ~/.virtualenvs/lovedays/bin/activate
python -m pip install --no-cache-dir -r requirements.txt
```

Chờ cài đặt hoàn tất và không có lỗi. `--no-cache-dir` giúp tránh giữ thêm bộ cài trong quota. Không cài Playwright hoặc các công cụ kiểm thử trình duyệt trên tài khoản miễn phí; website không cần chúng để hoạt động.

Lệnh clone trên dùng repository công khai. Repository riêng cần xác thực GitHub hoặc đưa file qua tab Files; không nhúng token vào URL hay commit token vào mã. Nếu `~/love` đã tồn tại và đúng repository này, vào thư mục đó để pull thay vì clone đè lên file có sẵn.

[GitHub qua HTTPS trên tài khoản Free](https://help.pythonanywhere.com/pages/ExternalVCS/).

## 5. Khởi tạo mật khẩu và kho riêng

Vẫn trong Bash đã kích hoạt virtualenv:

```bash
cd ~/love
export LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE
python server.py init-password
```

Nhập mật khẩu bạn muốn dùng hai lần tại hai lời nhắc ẩn. Để dùng mật khẩu đã yêu cầu trong hội thoại, nhập giá trị đó trực tiếp vào lời nhắc, không sửa JavaScript và không đưa mật khẩu vào dòng lệnh. Khi gõ, ký tự không hiện trên màn hình là bình thường.

Đọc vị trí kho thực tế:

```bash
python -c "from server import create_app; print(create_app().config['DATA_DIR'])"
```

Mặc định kho nằm tại `/home/USERNAME/.lovedays-private/<ma-du-an>/`, ngoài `~/love`, gồm `letters.json`, `images/`, `auth.sqlite3`, `secret.key` và file khóa. Ghi lại vị trí được in ra. Không tự tạo một JSON rỗng để thay kho hiện có.

Adapter và CLI dùng chung cách tính vị trí kho. Giữ ổn định đường dẫn dự án `~/love` khi cập nhật. Nếu dùng `LOVEDAYS_DATA_DIR` tùy chỉnh, phải đặt cùng một giá trị cho cả Bash CLI lẫn WSGI; chỉ export trong Bash không truyền biến sang Web app.

Nếu có thư/ảnh thật ở máy cũ, Git không tự chuyển chúng lên đây. Sao lưu và chuyển cả kho riêng qua Files trước khi dùng dữ liệu trên máy chủ mới; với SQLite đang chạy cần backup nhất quán. Giữ nguyên bản sao cũ đến khi kiểm tra xong. Xem [hướng dẫn dữ liệu riêng](BACKEND.md#nơi-lưu-riêng-và-quyền-truy-cập).

## 6. Tạo Web app và trỏ virtualenv

Trong tab Web:

1. Bấm Add a new web app.
2. Chấp nhận địa chỉ miễn phí `USERNAME.pythonanywhere.com` mà hệ thống đưa ra.
3. Chọn Manual configuration và Python 3.12, cùng phiên bản với virtualenv bước 4.
4. Ở Virtualenv, nhập `/home/USERNAME/.virtualenvs/lovedays`, thay USERNAME bằng username PythonAnywhere thật rồi lưu.
5. Nếu có Source code và Working directory, đặt `/home/USERNAME/love`.

[Luồng cấu hình Flask có sẵn và virtualenv](https://help.pythonanywhere.com/pages/Flask/).

## 7. Sửa file WSGI của Web app

Trong Web → Code, bấm liên kết WSGI configuration file. Thay nội dung file WSGI đó bằng đoạn hoàn chỉnh sau rồi Save:

```python
from pathlib import Path
import sys

project = str(Path.home() / "love")
if project not in sys.path:
    sys.path.insert(0, project)

from pythonanywhere_wsgi import application
```

Đây là file cấu hình của PythonAnywhere, thường nằm dưới `/var/www/`; không thay `server.py` bằng đoạn trên. Module `pythonanywhere_wsgi.py` trong repository tạo app hiện có và đặt mặc định Secure cookie, origin HTTPS cùng username, và SQLite DELETE journal. Không chứa mật khẩu.

Không chạy `python server.py serve`, `app.run()` hoặc Waitress trong file WSGI. PythonAnywhere tự quản lý tiến trình phục vụ web qua đối tượng `application`.

Hướng dẫn mặc định dùng miền US `.pythonanywhere.com`. Nếu tài khoản ở EU, cần đặt origin đúng trước khi import adapter, ví dụ bằng `os.environ['LOVEDAYS_PUBLIC_ORIGIN']` với địa chỉ HTTPS thật mà tab Web cấp. Không thêm `/api` hoặc `/love` vào origin.

## 8. Static files và HTTPS

Trong Web → Static files, thêm đúng hai mapping, thay USERNAME bằng username thật:

| URL | Directory |
| --- | --- |
| `/main/` | `/home/USERNAME/love/main` |
| `/fonts/` | `/home/USERNAME/love/fonts` |

Chỉ map hai thư mục công khai này. Không map URL `/` tới toàn bộ repo, không map `/api`, `.lovedays-private`, JSON thư hoặc thư mục ảnh riêng. API ảnh vẫn đi qua Flask để kiểm tra phiên.

Mở phần Security và bật Force HTTPS nếu tùy chọn này có trong Dashboard. Dùng địa chỉ bắt đầu bằng `https://` để đăng nhập, vì cookie của adapter được đặt Secure. Không cần mua SSL cho miền PythonAnywhere được cấp sẵn.

Cuối cùng bấm Reload ở đầu tab Web. [Static mappings](https://help.pythonanywhere.com/pages/StaticFiles/).

## 9. Kiểm tra sau triển khai

Mở đúng địa chỉ HTTPS trong tab Web:

1. Xác nhận avatar, font, hồ sơ, nhạc và animation tải được.
2. Nhấn 9 lần vào tim chưa mở thư; lần 10 mở một popup. Khoảng cách mỗi lần không quá 1,2 giây.
3. Nhập mật khẩu, tạo thư tiếng Việt có ảnh, sửa rồi mở lại theo ID.
4. Đăng nhập cùng URL trên thiết bị khác và đọc thư vừa tạo.
5. Tạo một thư thử để kiểm tra xóa có xác nhận.
6. Bấm Reload trong Web rồi kiểm tra thư và ảnh vẫn còn. Trước đó lưu xong mọi bản nháp.
7. Trong cửa sổ ẩn danh chưa đăng nhập, `/api/letters` phải trả 401; `/letters.json`, `/server.py`, `/pythonanywhere_wsgi.py` phải không tải được mã/dữ liệu riêng.
8. `/api/session` trả `passwordConfigured: true` sau khởi tạo. `authenticated: false` khi chưa đăng nhập là bình thường.

Chỉ khi hoàn tất các bước này mới xác nhận triển khai thật thành công. Kiểm thử local không chứng minh cấu hình filesystem, upload hoặc HTTPS của tài khoản từ xa đã đúng.

## 10. Cập nhật mã, mật khẩu và gia hạn

Sau mỗi lần sửa trên Windows, commit và push lên GitHub. Trong Bash của PythonAnywhere:

```bash
cd ~/love
source ~/.virtualenvs/lovedays/bin/activate
git pull --ff-only origin main
python -m pip install --no-cache-dir -r requirements.txt
```

Sau đó vào Web → Reload. Việc push GitHub không tự reload Web app trong cấu hình miễn phí này. Nếu pull báo thay đổi local hoặc không thể fast-forward, xử lý thay đổi đó thay vì reset hoặc xóa thư mục dự án.

Đổi mật khẩu trong Bash:

```bash
cd ~/love
source ~/.virtualenvs/lovedays/bin/activate
export LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE
python server.py init-password
```

Đổi mật khẩu thu hồi phiên đăng nhập cũ và giữ thư/ảnh. Tránh thao tác ghi từ website trong lúc quản trị kho hoặc sao lưu.

Mỗi tháng vào Web, bấm nút gia hạn ứng dụng trước hạn được hiển thị. Không dùng bot tạo traffic để thay thao tác gia hạn. Theo dõi quota trong Files; upload ảnh tính vào cùng 512 MiB với mã và virtualenv. Dùng ảnh dung lượng vừa phải, sao lưu kho riêng định kỳ và kiểm tra bản sao đọc được.

Nếu đã tạo Render trả phí, mã cấu hình trong repo không tự hủy dịch vụ đó. Chỉ sau khi dữ liệu được sao lưu/chuyển và bản miễn phí đã kiểm tra xong, vào tài khoản Render xử lý tài nguyên trả phí còn tồn tại để ngừng phát sinh chi phí.

## 11. Xử lý lỗi thường gặp

| Lỗi | Kiểm tra |
| --- | --- |
| ModuleNotFoundError | Đường dẫn project trong WSGI, Virtualenv của Web app và việc pip cài trong đúng môi trường |
| Không có python3.12 | Kiểm tra System Image; dùng một Python từ 3.10 trở lên có sẵn và chọn cùng phiên bản ở Web/virtualenv |
| Website báo lỗi 500/502 | Mở Error log trong tab Web, đọc traceback mới nhất sau Reload |
| UnixFileLock ... inherited across fork; construct a new instance | Cập nhật server.py có khóa riêng theo PID, rồi Web → Reload; xem hướng dẫn ngay dưới bảng |
| Hộp thư chưa có mật khẩu | Init trong đúng `~/love`, cùng kho mà Web app dùng; mật khẩu không đi theo Git |
| SQLite disk I/O hoặc database locked | Kiểm tra DELETE journal trong adapter và Bash; tránh quản trị/ghi cùng lúc; xem Error log trước khi sửa dữ liệu |
| Lỗi 403 khi đăng nhập | Dùng HTTPS, kiểm tra origin đúng hostname của tab Web; với EU cần override origin trước import adapter |
| Nhập sai nhiều lần bị khóa | Chờ hết retryAfter; đóng popup hoặc reload không xóa giới hạn |
| CSS, nhạc, avatar lỗi 404 | Kiểm tra hai static mappings và các file đã push đủ lên GitHub |
| Disk quota exceeded | Xem dung lượng Files; không xóa JSON/SQLite/khóa để giải phóng chỗ |
| Website tự ngừng sau một tháng | Vào Web gia hạn/kích hoạt lại theo nút Dashboard |

### Sửa lỗi UnixFileLock inherited across fork

Nếu Error log báo `RuntimeError: UnixFileLock ... letters.lock was inherited across fork; construct a new instance`, worker WSGI đang dùng đối tượng khóa được tạo trong tiến trình cha. Đây là lỗi vòng đời đối tượng khóa; không phải yêu cầu xóa hoặc tạo lại kho thư. Bản sửa trong server.py tạo một cặp RLock/FileLock riêng cho từng PID, vẫn khóa cùng file letters.lock và vẫn giữ khóa trong toàn bộ thao tác đọc–sửa–ghi. [Guard của thư viện filelock](https://py-filelock.readthedocs.io/en/latest/_modules/filelock/_api.html).

Trên máy Windows, sau khi có bản sửa trong thư mục dự án:

```powershell
Set-Location "C:\Users\Admin\Downloads\lovedays-main"
git add server.py tests/test_fork_locks.py docs/DEPLOY_FREE.md docs/TEST_REPORT.md
git commit -m "Fix inherited file locks on PythonAnywhere workers"
git push origin main
```

Trong Bash của PythonAnywhere:

```bash
cd ~/love
git pull --ff-only origin main
```

Sau khi pull thành công, vào Web → chọn ứng dụng → Reload. Chờ reload hoàn tất, tải lại website rồi mở hộp thư. Kiểm tra request GET /api/letters trả 200 và thử tạo/sửa một thư thử. Thư, ảnh, mật khẩu và đường dẫn kho giữ nguyên; không cần hạ phiên bản filelock. Nếu pull bị chặn bởi thay đổi local, kiểm tra git status và xử lý thay đổi trước khi tiếp tục, không reset hoặc xóa kho.

Mật khẩu chung vẫn cấp chung quyền đọc, tạo, sửa, xóa. Tên người gửi/người nhận không tạo tài khoản riêng. Chưa tạo tài khoản, deploy hoặc kiểm thử trên hạ tầng PythonAnywhere thay bạn.
