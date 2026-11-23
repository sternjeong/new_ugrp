# 3분커리 로고 (2026-11-17 확정)

## 구성

- **숫자 3**: 직선과 사선만으로 직접 그린 도형이다(점 12개). 색은 포스텍 오렌지 `#f6a700`.
- **분커리**: 검은고딕(Black Han Sans)을 도형(윤곽선)으로 바꾼 것이다. 글꼴이 없는 기기에서도 똑같이 보인다. 검은고딕은 SIL Open Font License라 로고에 쓸 수 있고, 글꼴 파일은 저장소에 넣지 않았다.
- 한글은 원래 비율 그대로이고, "분"은 3 높이의 60%다.

## 세 가지 형태

| 형태 | 모습 | 쓰는 곳 |
|---|---|---|
| **세로형** (`logo-stacked`) | 윗줄에 큰 3과 작은 "분", 아랫줄에 "커리". 3의 높이는 "커리"의 1.3배 | 포스터, 발표 자료 표지, 인스타 게시물처럼 자리가 넉넉한 곳 |
| **가로형** (`logo-horizontal`) | 한 줄에 3, 작은 "분", "커리". 가로:세로 약 3.6:1 | 사이트 머리글, 문서 머리말처럼 낮고 긴 자리 |
| **심볼** (`mark`) | 검은 둥근 사각형 위의 3 | 브라우저 탭 아이콘, 인스타 프로필, 앱 아이콘 |

## 파일

| 파일 | 내용 |
|---|---|
| `curri/static/brand/logo.svg` | 사이트 머리글에 쓰는 가로형. 바탕과 여백이 없다 |
| `curri/static/brand/logo-dark.svg` | 다크 모드 머리글용. 글자가 흰색이다 |
| `curri/static/brand/favicon.svg` | 브라우저 탭 아이콘(심볼) |
| `docs/brand/logo-stacked.svg`, `logo-stacked-1024.png`, `logo-stacked-512.png` | 세로형, 흰 바탕 |
| `docs/brand/logo-stacked-dark.svg`, `logo-stacked-dark-1024.png`, `logo-stacked-dark-512.png` | 세로형, 검은 바탕 |
| `docs/brand/logo-horizontal.svg`, `logo-horizontal-1600.png`, `logo-horizontal-800.png` | 가로형, 흰 바탕 |
| `docs/brand/logo-horizontal-dark.svg`, `logo-horizontal-dark-1600.png`, `logo-horizontal-dark-800.png` | 가로형, 검은 바탕 |
| `docs/brand/mark.svg`, `mark-1024.png`, `mark-512.png`, `mark-180.png` | 심볼 |

PNG 파일 이름의 숫자는 가로 픽셀 수다.

## 쓰는 규칙

- 가능하면 **검은 바탕 버전**을 쓴다. 오렌지는 흰 바탕 위 명암비가 약 2:1이라 작은 크기에서 3이 흐려진다.
- 로고 둘레에는 "분" 글자 높이만큼 빈자리를 둔다. `docs/brand/`의 파일에는 이 여백이 들어 있다.
- 세로형은 높이 80px, 가로형은 높이 28px보다 작게 쓰지 않는다. 그보다 작은 자리에는 심볼을 쓴다.
- 비율을 바꾸거나 늘리지 않는다. 색은 오렌지·검정·흰색만 쓴다.
- 포스텍 로고·심볼과 나란히 붙여 학교 공식 서비스처럼 보이게 하지 않는다. 오뚜기 3분 카레의 포장 글씨·색·배치를 닮게 고치지 않는다([디자인 가이드](../product/DESIGN_GUIDE.md) 5절).

## 다시 만들기

모양을 고치려면 `tools/build_logo.py` 위쪽의 숫자(비율, 획 굵기, 여백)를 바꾸고 다시 실행한다. 준비 방법은 그 파일 맨 위에 있다. PNG는 SVG를 브라우저로 그려서 저장한 것이다.
