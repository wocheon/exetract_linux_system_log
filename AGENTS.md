# AGENTS.md

## 1. Project Overview

이 프로젝트는 운영 서버에서 발생한 장애, 오류, 성능 저하 및 이상 현상의 원인을 분석하기 위해 필요한 로그와 메트릭을 안전하게 수집하는 도구를 개발한다.

수집된 결과물은 Codex, Claude Code, Gemini CLI 또는 기타 AI Agent가 운영 서버에 직접 접근하지 않고도 분석할 수 있는 형태로 제공한다.

이 프로젝트의 주된 결과물은 다음 중 하나 이상이 될 수 있다.

* Python 기반 로그 및 메트릭 수집 애플리케이션
* Bash 기반 보조 스크립트
* 설정파일 예제
* 민감정보 마스킹 모듈
* Prometheus 메트릭 수집 모듈
* GCP/AWS 시스템 이벤트 수집 모듈
* 수집 결과 검증 및 패키징 도구
* 운영 및 사용 문서

---

## 2. Primary Goals

다음 기능을 구현하는 것을 목표로 한다.

1. 특정 서버의 지정된 시간 범위에 해당하는 시스템 로그를 수집한다.
2. `journalctl` 및 `/var/log` 아래의 주요 로그를 수집한다.
3. 필요하면 특정 서비스, 프로세스 또는 애플리케이션 로그를 추가로 수집한다.
4. Prometheus가 연결되어 있다면 장애 시간대의 관련 메트릭을 수집한다.
5. GCP 또는 AWS 환경에서 시스템 이벤트, 유지보수 이벤트 및 인스턴스 관련 이벤트를 조회할 수 있도록 확장한다.
6. IP 주소, hostname, 사용자 정보 및 기타 민감정보를 마스킹한다.
7. 최종 수집 결과물을 `tar.gz` 형식으로 압축한다.
8. 일부 데이터 수집에 실패하더라도 수집 가능한 나머지 데이터는 보존한다.
9. 어떤 항목이 수집되었고 실패했는지 manifest와 실행 로그로 남긴다.

---

## 3. Default Environment

기본 대상 운영체제는 다음과 같다.

* Ubuntu 24.04 LTS

다른 운영체제는 설정값 또는 명령행 옵션으로 지정할 수 있어야 한다.

지원 후보 운영체제:

* Ubuntu 20.04 LTS
* Ubuntu 22.04 LTS
* Ubuntu 24.04 LTS
* Debian
* Rocky Linux
* Red Hat Enterprise Linux
* CentOS 계열

운영체제별 로그 위치, 명령어 옵션 및 서비스 이름이 다를 수 있으므로 OS별 처리는 모듈 또는 프로파일로 분리한다.

운영체제 감지는 가능하면 다음 파일을 기준으로 한다.

```bash
/etc/os-release
```

자동 감지가 실패하면 설정파일에 지정된 OS 값을 사용한다.

---

## 4. Safety Principles

이 프로젝트에서 가장 중요한 기준은 운영 서버의 안정성과 보안이다.

### 4.1 Read-only by Default

수집 도구는 기본적으로 읽기 전용으로 동작해야 한다.

기본 동작에서 다음 작업을 수행해서는 안 된다.

* 서비스 시작, 중지 또는 재시작
* 프로세스 종료
* 패키지 설치 또는 삭제
* 시스템 설정 변경
* 방화벽 변경
* 로그 삭제 또는 변경
* 로그 로테이션 강제 실행
* 파일 권한 또는 소유자 변경
* 시스템 재부팅
* 클라우드 리소스 생성, 수정 또는 삭제
* Prometheus 설정 변경
* 운영 데이터베이스 쿼리 실행

추가 패키지가 필요한 경우 자동으로 설치하지 말고 필요한 패키지와 설치 명령만 안내한다.

### 4.2 Resource Impact

로그 수집으로 운영 서버에 과도한 부하를 주어서는 안 된다.

다음을 고려한다.

* CPU 사용량
* 메모리 사용량
* Disk I/O
* 네트워크 전송량
* 임시 디스크 사용량
* 대용량 로그 압축 시 부하
* Prometheus 장기 범위 쿼리 부하

대용량 파일을 처리할 때는 가능하면 streaming 방식으로 처리한다.

전체 파일을 메모리에 로드하지 않는다.

### 4.3 Privilege Handling

가능하면 일반 사용자 권한으로 실행한다.

root 권한이 필요한 항목은 별도로 구분한다.

`sudo`가 필요한 명령은 실행 전에 다음 내용을 명시한다.

* 권한이 필요한 이유
* 실행할 정확한 명령
* 접근할 파일 또는 시스템 영역
* 예상되는 영향 범위

Agent는 승인 없이 임의로 권한을 상승시키거나 권한 설정을 변경해서는 안 된다.

---

## 5. Collection Time Range

로그와 메트릭은 기본적으로 사용자가 지정한 시간 범위를 기준으로 수집한다.

예시:

```yaml
collection:
  start_time: "2026-07-15T10:00:00+09:00"
  end_time: "2026-07-15T11:00:00+09:00"
  timezone: "Asia/Seoul"
```

시간 처리는 다음 기준을 따른다.

1. ISO 8601 형식을 우선 사용한다.
2. timezone을 명시적으로 처리한다.
3. 서버 timezone과 사용자 입력 timezone이 다르면 변환한다.
4. 시작 시간이 종료 시간보다 이후인 경우 실행을 중단한다.
5. 미래 시간이 포함되어 있으면 경고한다.
6. 메트릭과 로그에 동일한 시간 범위를 사용한다.

로그 형식상 지정된 시간 범위만 추출하기 어려운 경우 다음 순서를 따른다.

1. 해당 시간 범위에 해당하는 로테이션 파일을 선별한다.
2. 선별된 파일에서 가능한 범위만 필터링한다.
3. 필터링이 신뢰할 수 없으면 원본 파일 전체 복사를 고려한다.
4. 전체 파일을 복사한 경우 manifest에 그 사실과 이유를 기록한다.

---

## 6. Configuration

모든 주요 조건은 별도 설정파일에서 변경할 수 있어야 한다.

권장 기본 설정파일:

```text
config/default.yaml
```

민감정보가 포함된 설정파일 예제:

```text
config/local.yaml
```

`config/local.yaml`과 실제 인증정보는 Git에 커밋하지 않는다.

권장 설정 구조:

```yaml
project:
  name: "incident-collector"
  environment: "production"

target:
  os: "auto"
  hostname_alias: "target-01"
  timezone: "Asia/Seoul"

collection:
  start_time: "2026-07-15T10:00:00+09:00"
  end_time: "2026-07-15T11:00:00+09:00"
  output_directory: "./output"
  temporary_directory: "/tmp/incident-collector"
  continue_on_error: true
  max_file_size_mb: 1024
  max_total_size_mb: 5120

system_logs:
  enabled: true
  collect_journal: true
  collect_kernel_log: true
  collect_auth_log: true
  collect_login_history: true
  collect_command_history: true

log_paths:
  include:
    - "/var/log/syslog"
    - "/var/log/auth.log"
    - "/var/log/kern.log"
    - "/var/log/dmesg"
    - "/var/log/prompt.log"
  exclude:
    - "*.gz"
    - "*.old"

services:
  - name: "docker"
    enabled: false
    journal_unit: "docker.service"
    log_paths: []

  - name: "my-application"
    enabled: false
    journal_unit: "my-application.service"
    log_paths:
      - "/var/log/my-application/*.log"

prometheus:
  enabled: false
  base_url: "http://prometheus.example.internal:9090"
  bearer_token_env: "PROMETHEUS_BEARER_TOKEN"
  verify_tls: true
  timeout_seconds: 30
  step_seconds: 60
  job: "node-exporter"
  instance: ""
  queries: []

cloud:
  provider: "none"

  gcp:
    enabled: false
    project_id: ""
    instance_name: ""
    zone: ""
    include_cloud_logging: true
    include_system_events: true
    include_audit_logs: false

  aws:
    enabled: false
    region: ""
    instance_id: ""
    include_cloudwatch_logs: true
    include_system_events: true
    include_cloudtrail: false

masking:
  enabled: true
  mask_ip_addresses: true
  mask_hostnames: true
  mask_usernames: true
  mask_email_addresses: true
  mask_cloud_resource_ids: false
  preserve_loopback_addresses: true
  replacement_prefixes:
    ipv4: "IPV4"
    ipv6: "IPV6"
    hostname: "HOST"
    username: "USER"
    email: "EMAIL"

output:
  archive_format: "tar.gz"
  include_manifest: true
  include_checksums: true
  remove_unmasked_temporary_files: true
```

---

## 7. System Log Collection

Ubuntu 24.04 LTS에서는 `systemd-journald` 기반 로그 수집을 우선 고려한다.

### 7.1 Journal Logs

시간 범위를 지정할 때는 다음 형태를 기준으로 한다.

```bash
journalctl \
  --since "2026-07-15 10:00:00" \
  --until "2026-07-15 11:00:00" \
  --no-pager \
  --output=short-iso-precise
```

특정 서비스 로그:

```bash
journalctl \
  --unit docker.service \
  --since "2026-07-15 10:00:00" \
  --until "2026-07-15 11:00:00" \
  --no-pager \
  --output=short-iso-precise
```

Kernel 로그:

```bash
journalctl \
  -k \
  --since "2026-07-15 10:00:00" \
  --until "2026-07-15 11:00:00" \
  --no-pager \
  --output=short-iso-precise
```

호환성을 위해 `--kernel`보다 `-k` 사용을 우선 고려한다.

수집 대상에는 다음이 포함될 수 있다.

* 전체 system journal
* Kernel journal
* 지정된 systemd unit
* 이전 부팅 기록
* boot 관련 오류
* OOM Killer 기록
* filesystem 오류
* I/O 오류
* network interface 상태 변경
* service start/stop/restart 기록

### 7.2 `/var/log` Files

기본 검토 대상:

```text
/var/log/syslog
/var/log/auth.log
/var/log/kern.log
/var/log/dmesg
/var/log/cloud-init.log
/var/log/cloud-init-output.log
/var/log/apt/history.log
/var/log/apt/term.log
/var/log/unattended-upgrades/
/var/log/prompt.log
```

파일 존재 여부를 먼저 확인해야 한다.

OS나 rsyslog 설정에 따라 일부 파일이 존재하지 않을 수 있으므로 파일이 없다는 이유만으로 전체 수집을 실패 처리하지 않는다.

로테이션 로그도 고려한다.

예시:

```text
/var/log/syslog.1
/var/log/syslog.2.gz
/var/log/auth.log.1
```

압축 로그를 처리할 때는 원본을 변경하지 않고 `zcat`, `zgrep` 또는 Python의 `gzip` 모듈을 사용한다.

### 7.3 System Summary Snapshot

MVP는 수집기 실행 시점의 기본 서버 정보를 하나의 파일로 저장한다.

```text
metadata/system-summary.txt
```

수집 항목:

* OS와 kernel 정보
* CPU 사양
* 메모리 요약
* 디스크 사용 현황
* CPU 사용률 기준 상위 15개 프로세스
* 메모리 사용률 기준 상위 15개 프로세스

프로세스 정보에는 PID, PPID, process name, CPU 및 memory 비율만 포함한다.
command line과 사용자명은 secret 또는 개인정보 노출을 줄이기 위해 수집하지 않는다.
모든 명령은 `shell=True` 없이 argument list로 실행하고 timeout을 적용한다.
일부 명령이 실패하면 성공한 항목을 보존하고 manifest에 `partial`로 기록한다.
이 정보는 요청된 장애 시간 범위의 과거 상태가 아니라 실제 수집 실행 시점의 snapshot임을 결과 파일에 명시한다.

---

## 8. Command History and User Activity

`/var/log/prompt.log`에는 사용자가 실행한 command 이력이 포함될 수 있으므로 장애 시간대 분석에 활용한다.

단, command history에는 다음과 같은 민감정보가 포함될 수 있다.

* Password
* API key
* Access token
* Database connection string
* Private URL
* Secret environment variable
* 개인정보
* 고객정보

따라서 `/var/log/prompt.log`는 반드시 마스킹 파이프라인을 거친 후 결과물에 포함한다.

필요한 경우 다음 로그인 관련 정보를 수집할 수 있다.

```bash
last
lastlog
who
w
```

systemd journal 기반 로그인 이벤트도 확인할 수 있다.

```bash
journalctl \
  --unit ssh.service \
  --since "2026-07-15 10:00:00" \
  --until "2026-07-15 11:00:00"
```

Ubuntu 환경에 따라 SSH unit 이름은 다음 중 하나일 수 있다.

```text
ssh.service
sshd.service
```

실제 unit 존재 여부를 확인한 뒤 수집한다.

로그인 및 사용자 활동 수집 목적은 장애 시간대에 다음 이벤트가 있었는지 확인하는 것이다.

* SSH 로그인
* `sudo` 실행
* 사용자 전환
* 설정 변경 명령 실행
* 서비스 제어 명령 실행
* 배포 명령 실행
* 파일 삭제 또는 이동
* 패키지 설치 또는 업데이트
* 시스템 재부팅 또는 종료 요청

사용자명 마스킹이 활성화된 경우 동일한 원본 사용자는 결과물 전체에서 동일한 alias로 치환되어야 한다.

예시:

```text
alice   -> USER_001
deploy  -> USER_002
root    -> USER_ROOT
```

분석에 필요한 권한 관계를 보존하기 위해 `root`와 일반 사용자 구분은 유지할 수 있다.

---

## 9. Prometheus Metrics

Prometheus 연결정보는 설정파일 또는 환경변수로 입력할 수 있어야 한다.

인증정보를 설정파일에 평문으로 저장하지 않는다.

권장 환경변수:

```bash
export PROMETHEUS_BEARER_TOKEN="..."
```

Prometheus HTTP API의 `query_range`를 사용하여 지정된 시간대의 메트릭을 수집한다.

기본적으로 고려할 메트릭:

### CPU

```promql
100 - (
  avg by (instance) (
    rate(node_cpu_seconds_total{mode="idle"}[5m])
  ) * 100
)
```

### Memory

```promql
100 * (
  1 -
  (
    node_memory_MemAvailable_bytes
    /
    node_memory_MemTotal_bytes
  )
)
```

### Load Average

```promql
node_load1
```

```promql
node_load5
```

```promql
node_load15
```

### Filesystem Usage

```promql
100 * (
  1 -
  (
    node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}
    /
    node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}
  )
)
```

### Disk I/O

```promql
rate(node_disk_read_bytes_total[5m])
```

```promql
rate(node_disk_written_bytes_total[5m])
```

```promql
rate(node_disk_io_time_seconds_total[5m])
```

### Network

```promql
rate(node_network_receive_bytes_total{device!="lo"}[5m])
```

```promql
rate(node_network_transmit_bytes_total{device!="lo"}[5m])
```

### OOM and Process Pressure

```promql
increase(node_vmstat_oom_kill[5m])
```

```promql
node_pressure_cpu_waiting_seconds_total
```

```promql
node_pressure_memory_waiting_seconds_total
```

```promql
node_pressure_io_waiting_seconds_total
```

메트릭 이름은 설치된 exporter 버전과 설정에 따라 존재하지 않을 수 있다.

쿼리 실패 또는 빈 결과는 전체 수집 실패로 처리하지 않고 manifest에 기록한다.

수집 결과 형식은 다음 중 하나 이상을 지원한다.

* JSON
* CSV
* Prometheus API 원본 응답

분석 편의성을 위해 정규화된 CSV와 원본 JSON을 함께 저장하는 방식을 권장한다.

---

## 10. Cloud Provider Integration

Cloud Provider 연동은 선택 기능으로 구현한다.

기본값은 비활성화한다.

```yaml
cloud:
  provider: "none"
```

### 10.1 GCP

GCP에서는 다음 이벤트를 확인할 수 있도록 구성한다.

* Compute Engine 인스턴스 system event
* Host maintenance
* Instance reset, stop, start
* Preemption
* Automatic restart
* Live migration 관련 이벤트
* Serial port output
* Cloud Logging의 시스템 로그
* 필요 시 Audit Log

가능하면 다음 인증 순서를 사용한다.

1. Application Default Credentials
2. 연결된 Service Account
3. 사용자 지정 credential

인증키 파일을 프로젝트 저장소 또는 결과 압축파일에 포함해서는 안 된다.

권한은 최소 권한 원칙을 따른다.

예상되는 GCP 권한 예시:

* Logging Viewer
* Compute Viewer
* Monitoring Viewer

Audit Log는 사용자 및 관리자 활동 정보가 포함될 수 있으므로 기본 비활성화한다.

### 10.2 AWS

AWS에서는 다음 이벤트를 확인할 수 있도록 구성한다.

* EC2 instance state change
* Scheduled event
* Status check failure
* Stop, start, reboot, terminate 이벤트
* CloudWatch Logs
* CloudTrail 이벤트
* AWS Health 이벤트

가능하면 다음 인증 순서를 사용한다.

1. EC2 Instance Profile
2. Environment variables
3. AWS shared credentials/profile

Access Key와 Secret Key를 설정파일, 로그 또는 압축 결과물에 포함해서는 안 된다.

권한은 최소 권한 원칙을 따른다.

---

## 11. Sensitive Data Masking

모든 수집 결과는 압축 전에 마스킹되어야 한다.

마스킹 대상:

* IPv4 주소
* IPv6 주소
* Hostname
* FQDN
* 사용자명
* 이메일 주소
* MAC 주소
* Cloud instance ID
* Project ID
* Account ID
* Access token
* API key
* Authorization header
* Cookie
* Password 형태의 값
* Private key
* Database connection string
* 내부 URL
* 필요 시 file path 내 사용자명

마스킹은 동일한 원본 값에 대해 동일한 alias를 생성해야 한다.

예시:

```text
10.10.20.15       -> IPV4_001
10.10.20.16       -> IPV4_002
api-prod-01       -> HOST_001
user@example.com  -> EMAIL_001
```

다음 주소는 설정에 따라 보존할 수 있다.

```text
127.0.0.1
::1
0.0.0.0
```

마스킹 전 원본 데이터를 output 디렉터리에 저장하지 않는다.

마스킹 전 임시 파일이 필요한 경우 다음 조건을 지킨다.

1. 권한이 제한된 임시 디렉터리를 사용한다.
2. 예상하기 어려운 디렉터리명을 사용한다.
3. 작업 완료 후 삭제한다.
4. 삭제 실패 시 경고한다.
5. 임시 디렉터리 경로를 manifest에 기록한다.
6. 심볼릭 링크를 따라가지 않는다.

민감정보 마스킹 시 timestamp, PID, port, error code, metric value처럼 장애 분석에 필요한 정보는 가능한 한 보존한다.

---

## 12. Output Structure

권장 결과물 디렉터리 구조:

```text
incident-collection-20260715T100000-20260715T110000/
├── manifest.json
├── collection.log
├── README.md
├── checksums.sha256
├── metadata/
│   └── system-summary.txt
├── logs/
│   ├── journal/
│   │   ├── system.log
│   │   ├── kernel.log
│   │   └── services/
│   ├── var-log/
│   ├── application/
│   ├── command-history/
│   │   └── prompt.log
│   └── login-history/
├── metrics/
│   ├── prometheus/
│   │   ├── raw/
│   │   └── csv/
│   └── local/
├── cloud/
│   ├── gcp/
│   └── aws/
└── masking/
    └── masking-summary.json
```

최종 파일명 예시:

```text
incident-collection-TARGET_001-20260715T100000-20260715T110000.tar.gz
```

실제 hostname이나 IP 주소를 최종 파일명에 사용하지 않는다.

---

## 13. Manifest

`manifest.json`에는 최소한 다음 정보를 기록한다.

```json
{
  "schema_version": "1.0",
  "collector_version": "0.1.0",
  "started_at": "2026-07-15T11:10:00+09:00",
  "completed_at": "2026-07-15T11:12:30+09:00",
  "requested_time_range": {
    "start": "2026-07-15T10:00:00+09:00",
    "end": "2026-07-15T11:00:00+09:00",
    "timezone": "Asia/Seoul"
  },
  "target": {
    "alias": "TARGET_001",
    "os": "Ubuntu 24.04 LTS"
  },
  "masking": {
    "enabled": true,
    "completed": true
  },
  "collections": [
    {
      "name": "journal-system",
      "status": "success",
      "output": "logs/journal/system.log"
    },
    {
      "name": "auth-log",
      "status": "skipped",
      "reason": "file not found"
    },
    {
      "name": "prometheus-memory",
      "status": "failed",
      "reason": "connection timeout"
    }
  ],
  "warnings": [],
  "errors": []
}
```

수집 실패를 숨기지 않는다.

각 항목의 상태는 다음 값 중 하나를 사용한다.

```text
success
partial
failed
skipped
```

---

## 14. Error Handling

하나의 수집 항목이 실패하더라도 기본적으로 다음 항목을 계속 수집한다.

다만 다음 오류는 즉시 중단을 고려한다.

* 출력 디렉터리 안전성 검증 실패
* 임시 디렉터리 생성 실패
* 디스크 여유 공간 부족
* 마스킹 기능 초기화 실패
* 잘못된 시간 범위
* 설정파일 파싱 실패
* 결과물이 외부에 노출될 수 있는 권한 설정
* 심볼릭 링크 또는 path traversal 탐지
* 압축 결과물 무결성 검증 실패

종료 코드는 명확하게 구분한다.

권장 예시:

```text
0   전체 성공
1   일부 수집 실패
2   설정 오류
3   권한 오류
4   출력 공간 부족
5   마스킹 실패
6   패키징 실패
10  예상하지 못한 내부 오류
```

---

## 15. Implementation Guidelines

주 구현 언어는 Python 3을 권장한다.

이유:

* 날짜와 timezone 처리
* gzip 및 압축 로그 처리
* 정규표현식 기반 마스킹
* YAML/JSON 설정 처리
* Prometheus API 호출
* Cloud API 연동
* 구조화된 manifest 생성
* 단위 테스트 작성
* 예외 처리 및 부분 성공 관리

Bash는 다음 용도로 제한적으로 사용한다.

* 설치 없이 실행할 수 있는 최소 수집기
* Python 실행 환경 확인
* Python 애플리케이션 launcher
* 단순한 운영체제 정보 수집
* 긴급 상황용 fallback collector

권장 Python 버전:

```text
Python 3.10 이상
```

Ubuntu 24.04 LTS 기본 Python 환경과의 호환성을 고려한다.

---

## 16. Recommended Project Structure

초기 MVP는 사용성과 유지보수성을 위해 아래의 단순한 구조를 사용한다.
기능이 실제로 추가되기 전에는 빈 패키지나 provider별 디렉터리를 미리 만들지 않는다.

```text
.
├── AGENTS.md
├── README.md
├── pyproject.toml
├── config/
│   └── default.yaml
├── src/
│   └── incident_collector/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── os_detection.py
│       ├── output.py
│       ├── safety.py
│       ├── collectors/
│       │   ├── __init__.py
│       │   ├── system.py
│       │   ├── journal.py
│       │   └── files.py
├── tests/
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_files_collector.py
│   ├── test_journal_collector.py
│   ├── test_os_detection.py
│   ├── test_packaging.py
│   └── test_system_collector.py
└── .gitignore
```

MVP 모듈 경계:

* `cli.py`: 실행 순서와 종료 코드
* `config.py`: YAML 설정과 시간 범위
* `collectors/`: 독립된 로그 수집기
* `safety.py`: 입력 및 출력 경로 안전성
* `output.py`: 수집 결과 모델, manifest, archive, checksum
* `os_detection.py`: 현재 지원 OS 감지

마스킹, Prometheus 또는 Cloud 기능을 구현하는 단계에서만 필요한 모듈을 추가한다.

---

## 17. CLI Design

권장 CLI 사용법:

```bash
incident-collector collect \
  --config ./config/local.yaml \
  --start "2026-07-15T10:00:00+09:00" \
  --end "2026-07-15T11:00:00+09:00"
```

설정 검증:

```bash
incident-collector validate-config \
  --config ./config/local.yaml
```

실행 전 계획 출력:

```bash
incident-collector plan \
  --config ./config/local.yaml \
  --start "2026-07-15T10:00:00+09:00" \
  --end "2026-07-15T11:00:00+09:00"
```

마스킹 테스트:

```bash
incident-collector mask \
  --input ./sample.log \
  --output ./sample.masked.log
```

압축파일 검증:

```bash
incident-collector verify \
  ./incident-collection-TARGET_001-20260715T100000-20260715T110000.tar.gz
```

`plan` 명령은 실제 수집 전에 다음 정보를 보여줘야 한다.

* 수집 시간 범위
* 예상 수집 항목
* 필요한 권한
* 읽을 파일 목록
* 실행할 외부 명령
* Prometheus 쿼리 개수
* Cloud API 조회 여부
* 예상 임시 디렉터리
* 출력 위치
* 설정된 크기 제한
* 마스킹 적용 여부

---

## 18. Agent Working Rules

이 저장소에서 작업하는 AI Agent는 다음 규칙을 따른다.

### 18.1 Before Making Changes

코드를 수정하기 전에 다음을 수행한다.

1. `AGENTS.md`를 읽는다.
2. 기존 `README.md`와 프로젝트 구조를 확인한다.
3. 현재 구현과 요구사항의 차이를 정리한다.
4. 수정할 파일과 수정하지 않을 파일을 구분한다.
5. 운영 안전성에 영향을 주는 변경인지 확인한다.
6. 간단한 구현 계획을 먼저 제시한다.

### 18.2 Scope Control

요청받은 범위를 넘어 불필요한 구조 변경을 하지 않는다.

다음 작업은 명시적 요청 없이 수행하지 않는다.

* 프레임워크 전환
* 전체 프로젝트 재작성
* 설정파일 형식 변경
* CLI 호환성 파괴
* 대규모 dependency 추가
* Cloud Provider SDK 강제 의존
* 기존 수집 결과 형식 변경
* 기존 마스킹 규칙 완화

### 18.3 Operational Safety

Agent는 운영 서버에서 직접 다음 작업을 수행하지 않는다.

* 실제 로그 수집 실행
* root 권한 명령 실행
* 대용량 디렉터리 압축
* Cloud API 인증
* 외부 서버로 데이터 업로드
* 운영 Prometheus에 광범위한 쿼리 실행

Agent는 실행 가능한 코드와 명령을 제공할 수 있지만, 운영 환경 실행 전 다음을 함께 제공해야 한다.

* 사전 확인 명령
* 영향 범위
* 필요한 권한
* 예상 출력 경로
* 실패 시 정리 방법
* 롤백 또는 중단 방법

### 18.4 Security

다음 정보를 코드나 예제 설정에 하드코딩하지 않는다.

* Password
* API token
* Access key
* Secret key
* Private key
* 실제 IP
* 실제 hostname
* 실제 Project ID
* 실제 Account ID
* 실제 사내 URL

예제에는 명백한 placeholder를 사용한다.

```text
prometheus.example.internal
PROJECT_ID
INSTANCE_ID
TARGET_001
```

### 18.5 Dependencies

새 dependency를 추가하기 전에 다음을 확인한다.

* Python 표준 라이브러리로 구현 가능한가
* 유지보수가 활발한가
* 보안 취약점 위험이 있는가
* Ubuntu 24.04 LTS에서 설치 가능한가
* offline 환경에서도 사용할 수 있는가
* dependency를 optional extra로 분리할 수 있는가

Cloud Provider SDK는 가능하면 optional dependency로 분리한다.

예시:

```toml
[project.optional-dependencies]
prometheus = ["httpx>=0.27,<1"]
gcp = ["google-cloud-logging>=3,<4", "google-cloud-compute>=1,<2"]
aws = ["boto3>=1,<2"]
yaml = ["PyYAML>=6,<7"]
```

### 18.6 Testing

코드 변경 후 최소한 다음을 검증한다.

```bash
python -m compileall src
pytest
```

지원하는 경우 다음도 실행한다.

```bash
ruff check .
mypy src
```

실제 `/var/log` 또는 운영 Prometheus를 테스트 대상으로 사용하지 않는다.

테스트 fixture와 mock response를 사용한다.

---

## 19. Required Tests

최소 테스트 범위:

1. 설정파일 정상 파싱
2. 필수 설정 누락 감지
3. 잘못된 시간 범위 거부
4. timezone 변환
5. journal 명령 생성
6. 파일 존재 여부 처리
7. 로그 로테이션 파일 선별
8. gzip 로그 읽기
9. IPv4 마스킹
10. IPv6 마스킹
11. hostname 마스킹
12. username 마스킹
13. token 및 password 마스킹
14. 동일 값에 대한 일관된 alias
15. Prometheus API timeout 처리
16. Prometheus 빈 결과 처리
17. 부분 실패 manifest 생성
18. 임시 파일 정리
19. archive 생성
20. checksum 검증
21. path traversal 차단
22. symbolic link 처리
23. 파일 크기 제한
24. 전체 결과물 크기 제한

---

## 20. Acceptance Criteria

초기 버전은 최소한 다음 조건을 만족해야 한다.

* Ubuntu 24.04 LTS에서 실행 가능
* 시작 및 종료 시간을 지정할 수 있음
* `journalctl` 로그를 지정 시간대로 수집 가능
* `/var/log` 파일을 설정파일로 지정 가능
* `/var/log/prompt.log`를 선택적으로 수집 가능
* 로그인 이력을 선택적으로 수집 가능
* IPv4, hostname 및 username 마스킹 가능
* Prometheus 연결정보를 설정파일로 입력 가능
* Prometheus range query 결과를 JSON 또는 CSV로 저장 가능
* 수집 실패 항목을 manifest에 기록
* 최종 결과물을 `tar.gz`로 생성
* 원본 로그를 수정하지 않음
* 서비스 재시작이나 시스템 설정 변경을 수행하지 않음
* 실제 인증정보가 출력물에 포함되지 않도록 검증
* 최소 단위 테스트 제공

GCP 및 AWS 연동은 초기 버전 이후 별도 단계로 구현할 수 있다.

---

## 21. Recommended Implementation Phases

### Phase 1: Local System Collector

* CLI 기본 구조
* YAML 설정파일
* 시간 범위 처리
* OS 감지
* `journalctl` 수집
* `/var/log` 파일 수집
* manifest
* `tar.gz` 패키징

### Phase 2: Masking

* IP 마스킹
* hostname 마스킹
* username 마스킹
* token 및 password 패턴 마스킹
* 일관된 alias mapping
* 임시 파일 보호 및 정리

### Phase 3: Prometheus

* 연결 설정
* `query_range`
* 기본 node_exporter 쿼리
* raw JSON 저장
* CSV 변환
* timeout 및 부분 실패 처리

### Phase 4: User Activity

* `/var/log/prompt.log`
* `auth.log`
* SSH journal
* `last`, `lastlog`
* 사용자별 alias 처리

### Phase 5: Cloud Integration

* GCP Compute Engine 및 Cloud Logging
* AWS EC2, CloudWatch 및 CloudTrail
* 최소 권한 문서
* Cloud SDK optional dependency

### Phase 6: Hardening

* 크기 제한
* Disk 여유 공간 검증
* symlink 및 path traversal 차단
* archive 무결성 검증
* 성능 테스트
* 보안 테스트

---

## 22. Non-Goals

초기 범위에서는 다음 기능을 목표로 하지 않는다.

* 운영 서버 장애 자동 복구
* 서비스 자동 재시작
* 로그 자동 삭제
* 설정 자동 수정
* 방화벽 자동 변경
* 운영 서버에서 AI Agent 직접 실행
* 수집 결과 외부 SaaS 자동 업로드
* 사용자 명령 자동 차단
* SIEM 대체
* 장기 로그 보관 시스템 대체
* Prometheus 또는 Cloud Monitoring 대체

이 프로젝트는 분석에 필요한 증거를 안전하게 수집하는 도구이며, 자동 조치 시스템이 아니다.
