# GPU 관제 센터 (Kaggle, VM 전역)

GPU가 없는 VM에서 어느 레포의 `.ipynb`든 Kaggle GPU로 보내고, 상태·결과·주간 쿼터를 한 화면에서 본다. 이 폴더는 소스이고, 실제 설치·상태는 `~/.gpu-hub/`에 있다.

## 설치 / 갱신
```bash
tools/gpu/install.sh        # ~/.gpu-hub 에 kaggle 환경+앱, ~/.local/bin/gpuhub 생성 (코드 수정 후 재실행하면 갱신)
~/.gpu-hub/venv/bin/kaggle auth login --no-launch-browser   # 1회 인증 (GPU 사용에는 Kaggle 휴대폰 인증 필요)
gpuhub serve                # http://127.0.0.1:8765
```
원격 PC에서는 `ssh -L 8765:127.0.0.1:8765 <vm>` 후 브라우저로 연다. 대시보드는 로그인이 없으므로 127.0.0.1에만 바인드한다.

## 사용
- 어느 레포에서든 `gpuhub submit path/to/note.ipynb`, `gpuhub sync`, `gpuhub status`.
- 대시보드는 `~/.gpu-hub/config.json`의 `roots`(기본 `~/repos`) 아래 노트북을 레포별로 묶어 보여주고, 실험 기록에도 레포 이름이 표시된다.
- 결과는 `~/.gpu-hub/outputs/<run_id>/`에 내려받는다. 홈 디렉터리 밖의 노트북은 제출할 수 없다.

## 알아둘 점
- 쿼터는 공식 `kaggle quota` 원문과, 제출~종료 벽시계 시간으로 낸 로컬 추정치를 함께 표시한다. 주간 한도(기본 30h)는 `config.json`의 `weekly_gpu_hours`로 바꾼다.
- Colab 전제(Drive 마운트 등)의 노트북은 Kaggle용 수정이 필요하다.
