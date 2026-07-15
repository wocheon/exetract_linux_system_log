# Incident Collector MVP

Ubuntu 24.04 LTS 운영 서버에서 지정 시간대의 systemd journal과 명시적으로 지정한 로그 파일을 읽기 전용으로 수집하고, `manifest.json`을 포함한 `tar.gz` 및 SHA256 checksum을 생성하는 최소 구현입니다.

## 프로젝트 구조

기능을 찾기 쉽도록 실행 흐름을 여섯 개의 핵심 모듈로 유지합니다.

```text
src/incident_collector/
├── cli.py             # CLI와 전체 수집 순서
├── config.py          # YAML과 시간 범위 검증
├── os_detection.py    # Ubuntu 24.04 감지
├── output.py          # manifest, tar.gz, checksum
├── safety.py          # 경로와 symlink 검증
└── collectors/
    ├── system.py      # 서버 정보 스냅샷
    ├── journal.py     # journalctl 수집
    └── files.py       # 지정 파일 복사
```

새 수집 대상만 `collectors/`에 추가하고, 출력 관련 처리는 `output.py`에서 관리합니다.

## 안전 범위

- 서비스, 프로세스, 패키지, 시스템 설정을 변경하지 않습니다.
- `sudo` 또는 root 권한을 자동으로 획득하지 않습니다.
- `journalctl`은 `shell=True` 없이 인자 목록으로 실행합니다.
- 로그 원본 경로는 절대 경로만 허용하며 `..`, 심볼릭 링크, 비정규 파일을 거부합니다.
- 개별 수집 실패와 파일 미존재는 manifest에 `failed` 또는 `skipped`로 기록합니다.
- 임시 수집 디렉터리는 패키징 후 자동 삭제합니다.

> **MVP 보안 주의:** 현재 버전은 민감정보 마스킹을 구현하지 않았습니다. 생성된 archive에는 원본 로그 내용이 들어가므로 접근 권한이 제한된 로컬 경로에만 저장하고 외부로 전송하지 마십시오.

## 요구사항 및 설치

- Ubuntu 24.04 LTS
- Python 3.10 이상
- `journalctl` (journal 수집을 활성화한 경우)
- Ubuntu 기본 명령인 `uname`, `lscpu`, `free`, `df`, `ps`

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

도구는 패키지를 자동 설치하지 않습니다. 위 설치는 저장소 checkout에서 사용자가 직접 수행하는 개발 환경 설정입니다.

## 설정

기본 예시는 `config/default.yaml`입니다. Ubuntu에서 일반적으로 사용하는 `syslog`, `auth.log`, `kern.log`가 기본 경로에 포함되어 있으며, 존재하지 않는 파일은 오류가 아니라 `skipped`로 기록됩니다. 실제 실행용 설정은 별도 파일로 복사하고 시간을 지정합니다.

```bash
cp config/default.yaml config/local.yaml
```

```yaml
collection:
  start_time: "2026-07-15T10:00:00+09:00"
  end_time: "2026-07-15T11:00:00+09:00"
  timezone: "Asia/Seoul"
  output_directory: "./output"

log_paths:
  include:
    - "/var/log/syslog"
    - "/var/log/auth.log"
```

설정 파일에 비밀번호, API token, private URL 등의 인증정보를 저장하지 마십시오. 읽기 권한이 없는 로그는 자동 권한 상승 없이 실패로 기록됩니다.

## 실행

먼저 설정과 시간 범위만 검증할 수 있습니다.

```bash
incident-collector validate-config --config ./config/local.yaml
```

수집 실행:

```bash
incident-collector collect --config ./config/local.yaml
```

CLI 인자로 설정 시간 범위를 덮어쓸 수도 있습니다.

```bash
incident-collector collect \
  --config ./config/local.yaml \
  --start "2026-07-15T10:00:00+09:00" \
  --end "2026-07-15T11:00:00+09:00"
```

실행 전에는 대상 파일의 존재와 현재 사용자의 읽기 권한, output 및 임시 경로의 여유 공간을 확인하십시오.

```bash
test -r /var/log/syslog
test -w ./output || mkdir -p ./output
df -h ./output /tmp
```

예상 출력:

```text
output/
├── incident-collection-TARGET_001-20260715T100000-20260715T110000.tar.gz
└── incident-collection-TARGET_001-20260715T100000-20260715T110000.tar.gz.sha256
```

archive 내부에는 다음 서버 정보 파일이 기본으로 포함됩니다.

```text
metadata/system-summary.txt
```

이 파일에는 OS와 kernel, CPU·메모리 사양, 디스크 사용량, CPU 및 메모리 기준 상위 15개 프로세스가 들어갑니다. 프로세스 command line과 사용자명은 수집하지 않습니다. 서버 정보는 지정한 로그 시간대의 과거 값이 아니라 수집기 실행 시점의 스냅샷이며, 일부 명령을 사용할 수 없으면 가능한 내용은 보존하고 manifest 상태를 `partial`로 기록합니다.

checksum 검증:

```bash
cd output
sha256sum -c incident-collection-TARGET_001-20260715T100000-20260715T110000.tar.gz.sha256
```

실패 시 생성된 archive와 `.sha256` 파일만 삭제하면 됩니다. 도구는 원본 로그나 운영 서버 설정을 변경하지 않습니다.

## 종료 코드

| 코드 | 의미 |
|---:|---|
| `0` | 수집 성공 또는 설정상 생략만 발생 |
| `1` | 일부 수집 실패/부분 성공, archive는 생성됨 |
| `2` | 설정, 시간, OS 또는 안전 경로 검증 실패 |
| `6` | archive 또는 checksum 생성 실패 |

## 테스트

테스트는 `tmp_path`, mock runner, OS fixture만 사용하며 실제 `/var/log`와 system journal에 접근하지 않습니다.

```bash
python -m compileall src
pytest
```

## 현재 미구현 기능

- 민감정보 마스킹과 일관된 alias mapping
- rotation/gzip 로그의 시간 범위 필터링
- kernel 및 systemd unit별 journal 수집
- 로그인/command history 전용 수집기
- 크기 제한, 디스크 여유 공간 사전 검증, archive 내부 checksum 목록
- Prometheus, GCP, AWS 수집
- Debian/RHEL 계열 OS profile
