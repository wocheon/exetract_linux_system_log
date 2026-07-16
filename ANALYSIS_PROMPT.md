# 장애 로그 분석 프롬프트 템플릿

아래 코드 블록 전체를 AI Agent에 전달한다.
상황별로 바꿔야 하는 값은 맨 위의 `analysis_input` 영역에 모아두었다.
알 수 없는 값은 빈 문자열이나 빈 목록으로 두어도 된다.

```text
다음 incident-collection 결과물을 분석해라.

analysis_input:
  artifact: "[첨부한 tar.gz 파일 또는 압축 해제된 디렉터리 경로]"
  symptom: "[예: API 응답 지연 및 간헐적인 502 오류]"
  suspected_start: "2026-07-15 10:20:00"
  suspected_end: "2026-07-15 10:40:00"
  timezone: "Asia/Seoul"
  server_role: "[예: Nginx와 Python API가 실행되는 애플리케이션 서버]"
  related_services:
    - "[예: nginx.service]"
    - "[예: my-application.service]"
  questions:
    - "[예: 응답 지연의 직접적인 원인은 무엇인가?]"
    - "[예: CPU 또는 메모리 부족이 발생했는가?]"

분석 절차:

1. 가장 먼저 manifest.json을 확인한다.
   - 요청된 수집 시간 범위와 timezone
   - 실제 수집된 항목
   - 실패하거나 생략된 항목과 사유
   - 시간 필터 없이 전체 복사된 파일
   - 현재 자료로 확인할 수 없는 영역
   을 정리한다.

2. metadata/system-summary.txt를 확인한다.
   - OS와 kernel
   - CPU와 메모리 사양
   - 디스크 사용량
   - CPU 및 메모리 사용량이 높은 프로세스
   를 요약한다.
   이 정보는 장애 시각의 과거 상태가 아니라 수집기 실행 시점의 snapshot으로 취급한다.

3. metrics/prometheus 아래의 메트릭 파일을 시간순으로 분석한다.
   - CPU 사용률
   - 메모리 사용률
   - load average 1분
   - 그 밖에 실제로 수집된 메트릭

   suspected_start 전후의 값 변화, 최고값, 지속 시간과 급격한 변화를 확인한다.
   CPU, 메모리와 load average 사이의 연관성도 검토한다.

4. journal 및 지정 로그 파일에서 다음 이벤트를 찾는다.
   - error, warning, critical, fatal
   - timeout, connection refused, connection reset
   - OOM 또는 killed process
   - disk full 또는 no space left
   - I/O 및 filesystem 오류
   - 서비스 시작, 종료 또는 재시작
   - segmentation fault
   - 인증 및 권한 오류
   - 네트워크 연결 이상

5. related_services와 관련된 이벤트를 우선 확인한다.
   analysis_input에 없는 서비스도 장애와 연관된 근거가 발견되면 함께 분석한다.

6. 로그 이벤트와 메트릭 값을 동일한 timezone과 timestamp 기준으로 연결한다.
   단순히 가까운 시간에 발생했다는 이유만으로 인과관계라고 단정하지 않는다.

7. questions의 각 질문에 근거를 들어 답한다.
   자료가 부족하면 추측하지 말고 확인 불가 사유와 필요한 추가 자료를 제시한다.

결과 형식:

## 분석 범위와 데이터 품질
수집 성공, 실패 및 생략 내역과 분석 제한사항

## 시스템 요약
서버 사양, 디스크 현황과 수집 시점의 주요 프로세스

## 장애 타임라인
시각 | 이벤트 | 근거 파일 | 중요도

## 메트릭 이상 징후
장애 전후의 수치 변화와 로그 이벤트와의 연관성

## 가능한 원인
가능성이 높은 순서대로 작성하고 각 원인의 근거와 반대 근거를 함께 제시

## 질문별 답변
analysis_input.questions에 대한 답변

## 추가로 필요한 정보
현재 자료만으로 판단하기 어려운 사항과 추가 수집이 필요한 로그 또는 메트릭

## 결론
가장 가능성 높은 원인, 영향 범위와 확신 수준(높음/중간/낮음)

분석 규칙:

- 확인된 사실과 추정을 명확히 구분한다.
- 모든 주요 판단에 근거 파일명과 timestamp를 표시한다.
- 로그에 존재하지 않는 내용은 만들어내지 않는다.
- 수집 실패로 확인할 수 없는 내용은 "확인 불가"라고 작성한다.
- 전체 파일로 복사된 로그는 suspected_start부터 suspected_end 밖의 이벤트를 핵심 근거로 사용하지 않는다.
- 입력한 장애 추정 범위 밖에서 중요한 선행 또는 후속 이벤트가 발견되면 별도로 표시한다.
- 민감정보가 발견되면 답변에 그대로 반복하지 말고 마스킹한다.
- 운영 서버 설정 변경, 서비스 재시작 또는 자동 복구 명령은 제안하지 않는다.
- 압축 해제가 필요하면 별도 임시 디렉터리에서 읽기 전용 분석하고 원본 archive를 변경하지 않는다.
```

## 입력값 작성 예시

```yaml
analysis_input:
  artifact: "./incident-collection-TARGET_001-20260715T100000-20260715T110000.tar.gz"
  symptom: "10시 20분부터 API 응답 시간이 증가하고 일부 요청에서 502 오류 발생"
  suspected_start: "2026-07-15 10:20:00"
  suspected_end: "2026-07-15 10:40:00"
  timezone: "Asia/Seoul"
  server_role: "Nginx reverse proxy와 Python API 애플리케이션 서버"
  related_services:
    - "nginx.service"
    - "my-application.service"
  questions:
    - "502 오류가 애플리케이션 장애인지 시스템 자원 부족인지 확인해라."
    - "장애 직전에 서비스 재시작이나 OOM 이벤트가 있었는지 확인해라."
```
