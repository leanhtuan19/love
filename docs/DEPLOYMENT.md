# Triển khai từ GitHub và giữ đầy đủ tính năng

Bản media/bản đồ hiện tại dùng upload chia phần, không còn giới hạn ảnh 5 MB hoặc 25 MB tổng của phiên bản cũ. Xem [MEDIA_MAPS_AUDIO.md](MEDIA_MAPS_AUDIO.md) cho cấu hình và giới hạn thực tế; các ví dụ kiểm tra kích thước cũ bên dưới không phải quota hiện tại của ứng dụng.

**Muốn dùng hoàn toàn miễn phí:** làm theo [GitHub + PythonAnywhere Beginner](DEPLOY_FREE.md). Dự án đã có adapter WSGI cho gói này; giữ Flask, JSON và ảnh riêng. Các mục Render dưới đây là lựa chọn trả phí, không phải bước bắt buộc của phương án miễn phí.

Mã nguồn đã được sửa trực tiếp trong dự án. Các bước dưới đây là hướng dẫn để chủ repository triển khai; chưa có dịch vụ bên ngoài nào được tạo, chưa push và chưa thay đổi website đang chạy.

## 1. Môi trường đã xác định

- Repository được cấu hình: `https://github.com/leanhtuan19/love.git`, nhánh `main`.
- Frontend: `index.html`, HTML/CSS/JavaScript thuần trong `main/`, font trong `fonts/`; không cần npm, Vite hoặc đổi framework.
- Backend đã có: `server.py`, Python Flask + Waitress. JSON lưu thư; ảnh lưu trên đĩa riêng; SQLite lưu mật khẩu băm, phiên, CSRF và giới hạn thử mật khẩu. Không có PHP, bot hoặc webhook trong mã nguồn được kiểm tra.
- Trong lần kiểm tra này chưa có cấu hình hosting hoặc workflow triển khai cũ trong repository. Remote Git không chứng minh website production hiện đang dùng nền tảng nào.

| Nền tảng | Giao diện, nhạc, popup hồ sơ và animation | Hộp thư có xác thực, JSON và upload ảnh |
| --- | --- | --- |
| GitHub Pages | Có | Cần backend ở hosting phù hợp; Pages không chạy backend |
| Python hosting có ổ đĩa bền | Có | Có, dùng backend hiện tại |
| Vercel chỉ phục vụ frontend | Có | Cần proxy tới backend có ổ đĩa bền |
| Vercel Functions với JSON/SQLite đặt tại `/tmp` | Không phải cấu hình được đề xuất | Không giữ dữ liệu bền và không an toàn cho cơ chế lưu hiện tại |

GitHub Pages là hosting tĩnh và website theo repository mặc định có đường dẫn `/<repositoryname>/`. Vì remote hiện là `love`, địa chỉ dự kiến là `https://leanhtuan19.github.io/love/`, nếu Pages được bật và không có tên miền riêng. Địa chỉ `/lovedays/` trong README cũ có thể thuộc repository trước đó. [GitHub Pages: loại website và đường dẫn](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

## 2. Phương án đầy đủ: GitHub + Python web service + persistent disk

Triển khai cả website và `/api` trên cùng địa chỉ HTTPS giúp giữ nguyên mã frontend, cookie phiên và CSRF. GitHub tiếp tục quản lý mã nguồn; dữ liệu thư không lưu trong Git.

`render.yaml` cung cấp một cấu hình cụ thể cho Render: một Python web service, một instance và ổ đĩa 1 GB. Đây là dịch vụ trả phí khi bạn tự tạo trên Render; file cấu hình trong repository không tự tạo hay thanh toán dịch vụ. Persistent disk giữ dữ liệu qua restart/redeploy, chỉ có ở runtime và chỉ dùng cho một instance. Deploy có disk có thể gián đoạn trong thời gian thay phiên bản. [Render: persistent disks](https://render.com/docs/disks).

### 2.1. Đưa thay đổi lên GitHub

Chạy tại thư mục dự án, kiểm tra diff và chỉ stage các file mã nguồn/tài liệu cần thiết. Không stage kho dữ liệu riêng, `.env`, token hoặc mật khẩu:

```powershell
git status --short
git diff --stat
git diff
```

Sau khi đã rà soát, stage từng file bằng `git add <đường-dẫn-file>`; dùng tên thật từ `git status`, không nhập nguyên dấu ngoặc. Với các file cấu hình triển khai mới:

```powershell
git add render.yaml .python-version docs/DEPLOYMENT.md
```

Stage thêm các file chức năng đã sửa và tài liệu liên quan, sau đó:

```powershell
git diff --cached --stat
git diff --cached
git commit -m "Fix secret-letter gestures, mobile interactions and deployment"
git push origin main
```

Lệnh push cần quyền của tài khoản GitHub trên máy bạn. Tài liệu này không thực hiện commit hoặc push thay bạn.

### 2.2. Tạo web service

1. Đăng nhập Render, kết nối tài khoản GitHub có quyền đọc `leanhtuan19/love`.
2. Chọn **New → Blueprint**, chọn repository và nhánh `main`, dùng file `render.yaml`.
3. Xem lại gói tính phí và persistent disk trước khi đồng ý tạo. Cấu hình sử dụng plan ID `0.5c-512mb`, region `singapore`, một instance và disk 1 GB tại `/var/data`.
4. Cho phép build/deploy. Không đặt kho riêng vào thư mục source hoặc `/tmp`.
5. Dùng URL HTTPS thực tế Render cấp cho dịch vụ. Tên service trong Blueprint không đảm bảo URL chính xác, do tên có thể đã được dùng.

Các giá trị đã có trong Blueprint:

| Thiết lập | Giá trị |
| --- | --- |
| Python | `.python-version`: `3.12` |
| Build | `pip install -r requirements.txt` |
| Start | `python server.py serve --host 0.0.0.0 --port $PORT` |
| Health check | `/api/session` |
| `LOVEDAYS_DATA_DIR` | `/var/data/lovedays` |
| `LOVEDAYS_COOKIE_SECURE` | `true` |
| Số instance | `1` |

Render hỗ trợ `.python-version` không ghi patch và sẽ chọn patch mới nhất của nhánh 3.12. Nếu đã có biến `PYTHON_VERSION` trên Dashboard, biến đó có độ ưu tiên cao hơn; xóa biến cũ hoặc đặt phiên bản đầy đủ tương thích. [Render: phiên bản Python](https://render.com/docs/python-version).

Backend dùng `LOVEDAYS_PUBLIC_ORIGIN` nếu được đặt, nếu không sẽ lấy `RENDER_EXTERNAL_URL` do Render cung cấp. Vì vậy không cần biết trước URL lúc tạo Blueprint. Khi dùng tên miền riêng, đặt `LOVEDAYS_PUBLIC_ORIGIN=https://ten-mien-thuc-te-cua-ban` trong Environment rồi redeploy; giá trị là origin, không có đường dẫn `/love` hoặc `/api`. Chỉ dùng một origin chính thức cho thao tác ghi.

Blueprint theo nhánh `main` và tự deploy khi có commit mới sau khi đã kết nối. Hãy kiểm tra trạng thái build/deploy trên Dashboard; push thành công không đồng nghĩa deploy đã thành công. [Render: triển khai Flask từ GitHub](https://render.com/docs/deploy-flask), [cấu hình Blueprint](https://render.com/docs/blueprint-spec).

### 2.3. Khởi tạo mật khẩu hoặc chuyển kho cũ

**Nếu đã có thư/ảnh thật cần giữ:** trước khi bắt đầu sử dụng dịch vụ mới, dừng ghi ở máy chủ cũ, sao lưu và chuyển cả kho riêng qua kênh được bảo vệ vào `/var/data/lovedays`. Kho bao gồm `letters.json`, `images/`, `auth.sqlite3`, `secret.key` và các file liên quan. Dừng backend khi sao chép SQLite trực tiếp, hoặc dùng cơ chế backup SQLite nhất quán; không chỉ chép `letters.json` rồi bỏ ảnh hoặc khóa. Không thay thế thư mục đang có dữ liệu bằng một kho rỗng. Tài khoản dịch vụ cần sở hữu kho và có quyền đọc/ghi/tạo/xóa/đổi tên. Trên Linux dùng thư mục `0700`, các file riêng `0600`.

**Nếu đây là kho mới:** sau khi deploy đã chạy, mở **Shell** của chính web service, chạy:

```sh
python server.py init-password
```

Nhập mật khẩu đã chọn hai lần qua lời nhắc ẩn. Có thể dùng mật khẩu ban đầu đã yêu cầu trong hội thoại; không đưa giá trị vào mã nguồn, biến frontend, file JSON công khai hoặc lệnh có mật khẩu dạng rõ. Backend lưu băm scrypt có salt, không lưu mật khẩu gốc. Không có mật khẩu mặc định tự động cho máy chủ mới.

Chạy lệnh ở Shell runtime để ghi đúng persistent disk. Không đưa lệnh khởi tạo tương tác vào build hoặc pre-deploy. Trước khi có mật khẩu, hộp thư báo chưa thiết lập; nội dung website công khai vẫn xem được. Đổi mật khẩu cũng dùng `init-password`, thu hồi các phiên hiện có nhưng giữ thư/ảnh. Nếu đã cấu hình `LOVEDAYS_PASSWORD_HASH`, cần bỏ biến override đó trước khi đổi mật khẩu lưu trên đĩa. Hash override là bí mật phía máy chủ và cũng không được commit.

### 2.4. Kiểm tra sau khi deploy

1. Truy cập URL thật, xác nhận CSS/JS/font/nhạc không trả 404; kiểm tra các popup hồ sơ và nút nhạc.
2. Chạm/click 9 lần vào vùng nội dung không tương tác: chưa mở thư; lần 10 mở đúng một popup. Sau khi đóng, phải thực hiện lại đủ 10 lần.
3. Mở hộp thư trên thiết bị A, đăng nhập, tạo thư có ảnh. Truy cập cùng URL trên thiết bị B, đăng nhập và đọc đúng thư theo ID.
4. Thử sửa/xóa, thử sai mật khẩu đến ngưỡng, kiểm tra không truy cập được thư hoặc ảnh khi chưa đăng nhập.
5. Thử upload cả ảnh gần 5 MB và nhiều ảnh trong một lần để kiểm tra giới hạn của hosting/proxy thực tế.
6. Redeploy hoặc restart, xác nhận thư và ảnh còn nguyên. Health check thành công chỉ xác nhận API phiên chạy; nó không thay thế các bước xác thực, lưu dữ liệu và kiểm tra thiết bị.

Sao lưu cả kho riêng định kỳ và thử phục hồi. Không mở rộng nhiều instance dùng các kho khác nhau: JSON và SQLite cần cùng một persistent filesystem để khóa và phiên hoạt động nhất quán.

## 3. Giữ GitHub Pages cho giao diện công khai

Các đường dẫn `main/...` và `fonts/...` trong HTML là tương đối nên hoạt động dưới `/love/`. URL font trong CSS phải tương đối với chính file CSS: `main/css/effects.css` dùng `../../fonts/Lora-Variable.ttf`. Không đổi tài nguyên thành `/main/...`, vì dấu `/` đầu sẽ làm mất base path của repository.

Build chỉ xuất tài nguyên frontend được cho phép vào `_site`, không xuất backend, test, tài liệu hoặc kho riêng:

```powershell
python scripts/build_static.py
```

Để triển khai bằng workflow đã bổ sung:

1. Push mã và workflow lên GitHub.
2. Vào **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Vào **Actions → Deploy public site to GitHub Pages → Run workflow**, chọn nhánh `main`.
4. Đợi job deploy thành công và mở URL trong kết quả job.

Workflow chạy thủ công hoặc khi push vào main có thay đổi index.html, main/, fonts/, script build hoặc chính workflow. Sau khi bật Pages, các thay đổi frontend này sẽ tự cập nhật bản Pages; thay đổi riêng backend không kích hoạt bản tĩnh. Nếu tài khoản/repository chưa bật Pages hoặc thiếu quyền, cần xử lý thiết lập trên GitHub trước khi chạy lại. [GitHub: custom workflow cho Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Pages vẫn hiển thị trang, loading, animation, profile, âm nhạc và giao diện mở phong thư. `/api` không tồn tại trên Pages; popup sẽ giải thích cần bản có backend, không trả thư giả hoặc tự bỏ mật khẩu. Muốn sử dụng hộp thư đầy đủ, truy cập URL web service ở mục 2. Không commit thư riêng vào repo để giả lập backend.

Pages không cung cấp reverse proxy cho API. Frontend đã dùng URL theo base của trang: dưới `/love/` sẽ gọi `/love/api/...`; điều đó sửa đường dẫn nhưng không tạo máy chủ Python trên Pages. Không sửa đơn giản thành fetch cross-origin: cookie `SameSite=Strict`, CSRF, kiểm tra Origin và kiểm tra `Sec-Fetch-Site` của backend hiện được thiết kế cho cùng origin. Giữ thiết kế này bằng hosting chung hoặc reverse proxy có kiểm soát.

## 4. Vercel: frontend + backend hiện tại ở hosting có disk

Vercel có runtime Python/Flask, nhưng Functions có filesystem chỉ đọc ngoài vùng `/tmp` tạm thời. Không đặt JSON, SQLite, khóa ký phiên hoặc ảnh vào `/tmp`: dữ liệu có thể mất và các instance không dùng chung khóa. Functions còn giới hạn payload 4,5 MB, nhỏ hơn một ảnh tối đa 5 MB của website. Vì vậy bản này giữ backend hiện tại ở web service có persistent disk; không đưa Flask thành Vercel Function. [Vercel runtimes](https://vercel.com/docs/functions/runtimes), [Vercel Functions limits](https://vercel.com/docs/functions/limitations).

Nếu muốn tên miền frontend ở Vercel, dùng output tĩnh `_site` cùng external rewrite cho `/api`. Backend vẫn lưu dữ liệu tại ổ đĩa bền như mục 2. Chỉ thực hiện sau khi đã có địa chỉ backend HTTPS thật.

Ví dụ lệnh build với địa chỉ minh họa; phải thay `YOUR-BACKEND` bằng hostname thực tế:

```powershell
python scripts/build_static.py --backend-origin https://YOUR-BACKEND.onrender.com
```

Lệnh tạo `_site/vercel.json` với rewrite tới backend đã chọn. Cấu trúc rewrite là:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR-BACKEND.onrender.com/api/:path*"
    }
  ]
}
```

Để tránh Vercel tự nhận diện Flask từ `server.py` ở root, triển khai đúng thư mục output tĩnh, chọn framework **Other** và không có build bổ sung:

```powershell
Set-Location _site
npx vercel
```

Lệnh do bạn chạy cần Vercel CLI, Node/npm và tài khoản Vercel. Nó tạo preview để bạn kiểm tra. Sau khi cấu hình backend và xác nhận preview hoạt động, dùng `npx vercel --prod` trong chính `_site` để xuất production. Đây là hướng dẫn thao tác, không có deployment Vercel nào được thực hiện trong lần sửa này.

Tại backend, đặt `LOVEDAYS_PUBLIC_ORIGIN` đúng origin frontend Vercel đang kiểm tra. Khi chuyển sang production, đổi biến sang URL production cố định rồi redeploy backend. Preview ngẫu nhiên khác origin production sẽ bị chặn thao tác ghi theo thiết kế; không mở wildcard origin để bỏ qua. Cookie HttpOnly/Secure/Strict được trình duyệt dùng với origin frontend qua rewrite. Giữ `Cache-Control: no-store` cho `/api` và ảnh riêng, không bật cache cho nội dung đã xác thực. [Vercel: external rewrites](https://vercel.com/docs/routing/rewrites).

Sau khi proxy chạy, thử thực tế `Set-Cookie`, đăng nhập, CSRF, hết phiên, upload gần 5 MB và tổng nhiều ảnh. Giới hạn Vercel Function nêu trên khác với external rewrite; không suy ra rằng mọi proxy đều nhận được toàn bộ 25 MB upload. Chưa chạy thử proxy thật thì chưa thể xác nhận upload của môi trường này. Giới hạn IP phía backend hiện không tin `X-Forwarded-For` tùy ý; nhiều người qua một proxy có thể dùng chung bộ giới hạn IP. Muốn tách IP cần cấu hình proxy tin cậy cụ thể, không tin header do client tự gửi.

Muốn tự deploy frontend Vercel theo push GitHub, có thể bổ sung pipeline xuất đúng `_site` hoặc một project frontend riêng sau khi đã chọn backend thật. Chưa thêm root `vercel.json` tự deploy với hostname giả và chưa thay nền tảng đang chạy. Render Blueprint đã cung cấp đường GitHub → tự deploy đầy đủ ngay khi bạn kết nối dịch vụ và khởi tạo mật khẩu.

## 5. Thông số và nội dung cần chỉnh

| Muốn đổi | Vị trí |
| --- | --- |
| Nội dung thư | Mở hộp thư trên bản có backend và dùng tạo/sửa/xóa; dữ liệu nằm trong kho riêng |
| Số lần chạm, khoảng cách giữa hai lần chạm | `SECRET_CONFIG` trong `main/js/letters.js`; mặc định 10 lần, 1200 ms giữa hai lần |
| Mật khẩu | `python server.py init-password` trên máy chủ có kho riêng |
| Giới hạn sai, thời gian chờ và thời hạn phiên | `create_app()` trong `server.py` |
| Giới hạn ảnh | `MAX_IMAGES`, `MAX_IMAGE_BYTES` trong `server.py`; frontend lấy cấu hình qua API |
| Người gửi/người nhận | `PEOPLE` trong `server.py`; ID đã có dữ liệu phải giữ ổn định |
| Thông tin hồ sơ | `main/js/profiles.js` |
| Ngày bắt đầu, hiệu ứng tim và nhạc | `main/js/app.js`, `index.html`, `main/music/` |
| Dữ liệu mẫu | `docs/letters.example.json`; chỉ minh họa, không tự import lên kho thật |

Mật khẩu chung mở quyền chung đọc/tạo/sửa/xóa; chọn tên người gửi hoặc người nhận không tạo tài khoản hoặc quyền riêng. JSON và ảnh riêng không nằm trong static output hoặc public-file allowlist của backend.

## 6. Phạm vi đã và chưa xác nhận

Kết quả chạy backend/trình duyệt tại máy phát triển được ghi trong [TEST_REPORT.md](TEST_REPORT.md). Tài liệu triển khai này đối chiếu cơ chế nền tảng bằng nguồn chính thức; chưa kết nối tài khoản Render/Vercel, chưa tạo dịch vụ tính phí, chưa chạy GitHub Actions trên repository từ xa và chưa kiểm thử trên iPhone/Android thật. Các bước kiểm tra production ở trên vẫn cần thực hiện sau khi chủ repo triển khai.
