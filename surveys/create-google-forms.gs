/**
 * UGRP 커피챗 설문 2개 생성기 — Google Apps Script V8
 * https://script.google.com/ 에서 새 프로젝트의 Code.gs에 붙여넣고
 * createUGRPSurveys를 실행하세요. 외부 라이브러리/API 키는 필요 없습니다.
 * 생성 결과는 실행 로그에 표시됩니다. 자동으로 게시하지 않습니다.
 */
function createUGRPSurveys() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const results = [
      createSurveyOnce_('UNDERGRADUATE_V2', '연구실 선택 경험과 정보 수요 조사 — 학부생 대상', buildUndergraduate_),
      createSurveyOnce_('GRADUATE_V2', graduateTitle_(), buildGraduate_)
    ];
    results.forEach(function (result) {
      console.log(JSON.stringify(result, null, 2));
    });
    return results;
  } finally {
    lock.releaseLock();
  }
}

/** 기존 프로젝트에서 학부생 수정본만 생성합니다. 재실행 시 같은 수정본을 반환합니다. */
function createUpdatedUndergraduateSurvey() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    return createSurveyOnce_('UNDERGRADUATE_V2',
      '연구실 선택 경험과 정보 수요 조사 — 학부생 대상', buildUndergraduate_);
  } finally {
    lock.releaseLock();
  }
}

/** 같은 프로젝트에서 생성한 대학원생 폼의 문항을 직접 수정합니다. */
function updateGraduateSurvey() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const props = PropertiesService.getUserProperties();
    const keys = ['GRADUATE_V2', 'GRADUATE'];
    const key = keys.find(function (candidate) {
      return props.getProperty('UGRP_COFFEECHAT_V1_' + candidate + '_FORM_ID');
    });
    if (!key) {
      return createSurveyOnce_('GRADUATE_V2',
        graduateTitle_(), buildGraduate_);
    }
    const prefix = 'UGRP_COFFEECHAT_V1_' + key;
    if (props.getProperty(prefix + '_READY') !== 'true') {
      throw new Error('이전 폼 생성이 완료되지 않았습니다. 이전 실행 로그를 확인해 주세요.');
    }
    const form = FormApp.openById(props.getProperty(prefix + '_FORM_ID'));
    const items = form.getItems();
    // 변경 전에 수정할 문항을 모두 확인합니다.
    const questions = ['G1.', 'G2.', 'G5.', 'G6.', 'G9.'].map(function (id) {
      const matches = items.filter(function (item) {
        return item.getTitle().indexOf(id) === 0;
      });
      if (matches.length !== 1) {
        throw new Error(id + ' 문항을 하나로 식별할 수 없습니다. 편집 화면에서 확인해 주세요: ' + form.getEditUrl());
      }
      return matches[0];
    });
    const g1 = questions[0].asMultipleChoiceItem();
    const g2 = questions[1].asMultipleChoiceItem();
    const g5 = questions[2].asCheckboxItem();
    const g6 = questions[3].asCheckboxItem();
    const g9 = questions[4].asMultipleChoiceItem();
    const conditionPages = items.filter(function (item) {
      return item.getType() === FormApp.ItemType.PAGE_BREAK && item.getTitle() === '참여 조건';
    });
    if (conditionPages.length !== 1) {
      throw new Error('참여 조건 섹션을 식별할 수 없습니다: ' + form.getEditUrl());
    }
    form.setTitle(graduateTitle_()).setDescription(graduateDescription_());
    conditionPages[0].asPageBreakItem().setHelpText(graduateConditions_());
    g1.setTitle('G1. 현재 재학 중인 과정은 무엇인가요?')
      .setChoiceValues(['석사', '박사', '통합']);
    g2.setTitle('G2. 현재 소속 학과 또는 대학원 조직은 어디인가요?')
      .setChoiceValues(graduateDepartments_())
      .setHelpText('본인이 소속된 학과 또는 대학원 조직 하나를 선택해 주세요.');
    g5.setTitle(graduateRewardTitle_())
      .setChoiceValues(graduateRewards_())
      .setHelpText(graduateRewardHelp_());
    g5.setValidation(FormApp.createCheckboxValidation()
      .requireSelectAtMost(2).setHelpText('최대 2개까지 선택해 주세요.').build());
    graduateDetail_(form, g2, 'G2-기타. 기타 소속 학과 또는 대학원 조직을 적어 주세요.', '기타');
    graduateDetail_(form, g5, 'G5-기타. 위 항목 외의 비금전 보상을 적어 주세요.', '위 항목 외의 비금전 보상');
    graduateDetail_(form, g6, 'G6-기타. 위 항목 외의 기대를 적어 주세요.', '위 항목 외의 기대');
    graduateDetail_(form, g9, 'G9-기타. 위 항목 외의 이유를 적어 주세요.', '위 항목 외의 이유');
    const result = {
      title: form.getTitle(),
      editUrl: form.getEditUrl(),
      respondentUrl: form.getPublishedUrl(),
      note: '기존 대학원생 폼의 제목·소개·참여 조건·G1·G2·G5를 수정하고 기타 입력 칸을 추가했습니다. 기존 응답에는 이전 선택지가 남아 있을 수 있습니다.'
    };
    console.log(JSON.stringify(result, null, 2));
    return result;
  } finally {
    lock.releaseLock();
  }
}

function graduateTitle_() {
  return '학부생과의 대학원/연구실 Q&A 커피챗 참여 조건 조사 — 대학원생 대상';
}

function graduateDescription_() {
  return '안녕하세요. 2026 UGRP 기술창업트랙으로 연구/개발 중인 오뚜기부대 팀의 팀장 최선우입니다. 저희 팀은 아이템이 제공하는 서비스 중 하나로, POSTECH 대학원 진학 및 연구참여를 위해, 연구실을 알아보는 학부생과 대학원생의 1:1 대화 연결 서비스를 검토하고 있습니다. 현재 POSTECH 대학원에 재학 중이며 연구실에 소속해 활동하는 분을 대상으로 참여 의향과 기대 조건을 알아보고자 합니다.\n\n' +
    '설문 예상 소요 시간은 약 2~3분입니다. 이름, 이메일, 소속 연구실명은 수집하지 않으며, 응답은 서비스 기획을 위한 통계 분석 목적으로만 사용됩니다. 응답은 자율적으로 진행하며 원하지 않으면 제출하지 않고 종료할 수 있습니다. 이 설문에 응답해도 실제 커피챗 참여나 보상 지급이 확정되는 것은 아님을 알려드립니다.';
}

function graduateConditions_() {
  return '아래 질문에서는 다음 조건의 커피챗을 가정해 주세요.\n\n' +
    '• POSTECH 연구실을 알아보는 자대 학부생 1명과 온라인으로 20분 간 대화합니다.\n' +
    '• 학부생의 질문은 대학원생에게 적어도 커피챗 하루 전에는 전달되며, 이를 참고해 자율적으로 준비 가능합니다.\n' +
    '• 커피챗 진행 시간대의 결정권은 대학원생에게 우선적으로 주어집니다.\n' +
    '• 본인이 경험한 연구실 생활·연구 참여에 관해 이야기합니다.\n' +
    '• 연구실의 비공개 정보나 답하기 어려운 질문에는 답하지 않아도 됩니다.\n' +
    '• 금전 보상은 커피챗의 각 회당 실제 수령하는 금액을 뜻합니다.';
}

function graduateRewardTitle_() {
  return 'G5. 금전 보상이 없다면, 어떤 보상이 참여를 고려하는 데 가장 도움이 될까요? 최대 2개까지 선택 가능합니다.';
}

function graduateRewards_() {
  return ['관심사가 맞는 학부 연구 참여 지원자와의 연결', '본인이 속한 연구실의 홍보',
    '멘토링 활동 확인서·기록', '다른 연구자·대학원생과의 교류 기회',
    '위 항목 외의 비금전 보상', '보상 없이도 참여 가능', '어떤 비금전 보상으로도 참여 의향 없음'];
}

function graduateRewardHelp_() {
  return '마지막 두 보기는 각각 단독으로 선택해 주세요.\n상품권·기프티콘은 현금성 보상으로 판단해 이 질문에서 제외합니다.';
}

/** 해당 보기 선택자만 작성하는 선택 입력 칸. 재실행 시 기존 칸을 재사용합니다. */
function graduateDetail_(form, parent, title, choice) {
  const matches = form.getItems().filter(function (item) {
    return item.getTitle() === title;
  });
  if (matches.length > 1) throw new Error('중복된 기타 입력 문항이 있습니다: ' + title);
  const item = matches.length ? matches[0].asTextItem() : form.addTextItem();
  item.setTitle(title).setRequired(false)
    .setHelpText('앞 문항에서 ‘' + choice + '’를 선택한 경우에만 작성해 주세요. 다른 보기를 선택했다면 건너뛰세요. 이름·이메일·소속 연구실명은 적지 마세요.');
  // 앞에 있던 칸을 옮기면 부모 문항의 인덱스가 하나 감소합니다.
  const targetIndex = parent.getIndex() + (item.getIndex() < parent.getIndex() ? 0 : 1);
  if (item.getIndex() !== targetIndex) form.moveItem(item, targetIndex);
  return item;
}

function graduateDepartments_() {
  return ['수학과', '물리학과', '화학과', '생명과학과', '신소재공학과', '기계공학과',
    '산업경영공학과', '전자전기공학과(전자컴퓨터융합)', '화학공학과', '컴퓨터공학과',
    '반도체공학과', '의공학과', 'POSTECH 융합대학원', '인공지능', '친환경에너지', '기타'];
}

function createSurveyOnce_(key, title, build) {
  const props = PropertiesService.getUserProperties();
  const prefix = 'UGRP_COFFEECHAT_V1_' + key;
  const existingId = props.getProperty(prefix + '_FORM_ID');
  let form;
  if (existingId) {
    form = FormApp.openById(existingId);
    if (props.getProperty(prefix + '_READY') !== 'true') {
      throw new Error('이전 생성이 중단된 폼이 있습니다. 중복 생성을 막기 위해 멈춥니다. 편집 링크에서 확인하세요: ' + form.getEditUrl());
    }
  } else {
    form = FormApp.create(title, false);
    props.setProperty(prefix + '_FORM_ID', form.getId());
    console.log('생성 중인 폼 편집 링크: ' + form.getEditUrl());
    form.setCollectEmail(false)
      .setLimitOneResponsePerUser(false)
      .setPublishingSummary(false)
      .setShuffleQuestions(false)
      .setProgressBar(true)
      .setIsQuiz(false);
    build(form);
    const sheet = SpreadsheetApp.create(title + ' — 응답');
    props.setProperty(prefix + '_SHEET_ID', sheet.getId());
    form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
    props.setProperty(prefix + '_READY', 'true');
  }
  const result = {
    title: form.getTitle(),
    editUrl: form.getEditUrl(),
    respondentUrl: form.getPublishedUrl(),
    responseSheetUrl: 'https://docs.google.com/spreadsheets/d/' + props.getProperty(prefix + '_SHEET_ID') + '/edit',
    note: '미게시 상태로 생성되었습니다. 폼 편집 화면에서 미리보기와 응답자 접근 설정을 확인한 뒤 게시하세요.'
  };
  console.log('완료: ' + JSON.stringify(result));
  return result;
}

function mc_(form, title, choices, help) {
  const item = form.addMultipleChoiceItem().setTitle(title).setRequired(true);
  if (choices) item.setChoiceValues(choices);
  if (help) item.setHelpText(help);
  return item;
}

function cb_(form, title, choices, help) {
  const validation = FormApp.createCheckboxValidation()
    .requireSelectAtMost(2)
    .setHelpText('최대 2개까지 선택해 주세요.')
    .build();
  const item = form.addCheckboxItem()
    .setTitle(title)
    .setChoiceValues(choices)
    .setRequired(true)
    .setValidation(validation);
  if (help) item.setHelpText(help);
  return item;
}

function section_(form, title, help) {
  const page = form.addPageBreakItem().setTitle(title);
  if (help) page.setHelpText(help);
  return page;
}

function buildUndergraduate_(form) {
  form.setDescription(
    '안녕하세요. UGRP 팀은 학부생이 연구실을 선택할 때 어떤 정보를 필요로 하는지 알아보고 있습니다. 현재 학부생이라면 연구참여 경험이 없어도 응답할 수 있습니다. 연구참여에는 학부연구생, 연구실 인턴, 단기 연구 프로젝트를 포함합니다. 수업 실습만 참여한 경우는 제외합니다.\n\n' +
    '예상 소요 시간은 약 3~4분입니다. 이름, 이메일, 소속 연구실명은 수집하지 않으며, 응답은 서비스 기획을 위한 통계 분석에 사용합니다. 응답은 자율적으로 진행하며 원하지 않으면 제출하지 않고 종료할 수 있습니다. 정답은 없으니 본인의 경험에 가장 가까운 답을 선택해 주세요.'
  ).setConfirmationMessage('응답해 주셔서 감사합니다. 연구실 선택에 필요한 정보를 이해하고 UGRP 서비스를 설계하는 데 활용하겠습니다.');
  form.addSectionHeaderItem().setTitle('응답 대상과 배경');
  const u1 = mc_(form, 'U1. 현재 학적 상태는 무엇인가요?', null);
  const pageB = section_(form, '연구실 선택 기준',
    '연구실을 찾아본 경험이 있다면 가장 최근의 선택 당시를 기준으로 답해 주세요. 경험이 없다면 앞으로 선택할 때의 기준을 답해 주세요.');
  mc_(form, 'U2. 포항공과대학교에서 현재 주전공은 무엇인가요?',
    ['수학과', '물리학과', '화학과', '생명과학과', '신소재공학과', '기계공학과',
     '산업경영공학과', '전자전기공학과', '컴퓨터공학과', '화학공학과', '의공학과', '반도체공학과']);
  form.addSectionHeaderItem()
    .setTitle('U3. 연구실을 선택할 때 얼마나 중요한가요?')
    .setHelpText('각 항목을 1~5점으로 평가해 주세요. 1 전혀 중요하지 않음 · 2 별로 중요하지 않음 · 3 보통 · 4 중요함 · 5 매우 중요함.\n연구실을 선택한 경험이 있다면 당시 기준으로, 없다면 앞으로의 기준으로 답해 주세요.');
  [
    '연구 주제가 내 관심사와 맞는 정도', '배울 수 있는 연구 방법과 기술', '실제로 맡게 될 업무와 역할',
    '교수·대학원생의 지도와 피드백', '연구실 분위기와 구성원 간 관계',
    '참여 시간·기간과 학업을 병행할 수 있는 정도', '진학·취업에 도움이 되는 경험'
  ].forEach(function (title, index) {
    form.addScaleItem()
      .setTitle('U3-' + (index + 1) + '. ' + title)
      .setBounds(1, 5)
      .setLabels('전혀 중요하지 않음', '매우 중요함')
      .setRequired(true);
  });
  cb_(form, 'U4. 관심 연구 주제가 비슷한 연구실 두 곳 중 하나를 선택한다면, 최종 선택을 가장 크게 좌우할 기준은 무엇인가요? 최대 2개를 선택해 주세요.',
    ['더 체계적인 지도와 피드백', '나에게 잘 맞는 분위기와 구성원 관계', '더 명확한 업무·역할과 성장 기회',
     '더 유연한 참여 시간·기간', '더 좋은 연구 성과·평판과 진로 기회', '더 좋은 보수·연구 지원 조건', '위 항목 외의 기준']);
  cb_(form, 'U5. 연구실을 찾거나 비교할 때 주로 이용한 정보원은 무엇인가요? 최대 2개를 선택해 주세요.',
    ['연구실 홈페이지·논문·프로젝트 소개', '교수와의 직접 상담', '해당 연구실 대학원생과의 대화',
     '연구참여 경험이 있는 학부생·선배와의 대화', '연구실을 찾아본 적이 없음'],
    '‘찾아본 적이 없음’은 단독으로 선택해 주세요.');
  section_(form, '실제 연구참여 경험',
    '여러 연구실에서 참여했다면 가장 최근에 참여한 한 곳을 기준으로 답해 주세요. 현재 참여 중이라면 지금까지의 경험을 기준으로 답해 주세요.');
  const u7 = mc_(form, 'U7. 해당 연구실에서의 연구참여 경험에 전반적으로 얼마나 만족하나요?', null,
    '연구참여 경험이 없다면 ‘연구참여 경험이 없음’을 선택해 주세요.');
  const pageExperience = section_(form, '연구참여 만족 요인과 기대',
    '가장 최근에 참여한 한 연구실을 기준으로 답해 주세요.');
  cb_(form, 'U8. 만족하거나 불만족하게 된 데 가장 큰 영향을 준 요인은 무엇인가요? 최대 2개를 선택해 주세요.',
    ['연구 주제와 내 관심사의 일치 정도', '지도·피드백의 질과 빈도',
     '연구실 분위기와 구성원 관계', '업무량·참여 시간과 학업 병행', '보수·연구 지원 조건',
     '진학·취업에 도움이 된 정도', '위 항목 외의 요인']);
  mc_(form, 'U9. 참여 전에 기대했던 내용과 실제 경험은 얼마나 일치했나요?',
    ['1 전혀 일치하지 않음', '2 별로 일치하지 않음', '3 보통', '4 대체로 일치함', '5 매우 일치함']);
  const pageD = section_(form, '더 필요한 정보와 대화 수요');
  cb_(form, 'U10. 연구실을 선택하기 전에 추가로 알 수 있다면 가장 도움이 될 정보는 무엇인가요? 최대 2개를 선택해 주세요.',
    ['학부생이 실제로 맡는 업무와 하루 일과', '지도·피드백 방식과 질문하기 쉬운 정도',
     '연구실 분위기와 구성원 간 소통 방식', '주당 참여 시간·기간과 학업 병행 가능성',
     '필요한 사전 지식·기술과 선발 기준', '현재 진행 중인 연구 주제와 프로젝트',
     '보수·지원 조건과 진로 연결 기회', '추가 정보가 필요하지 않음', '위 항목 외의 정보'],
    '경험자는 당시 부족했던 정보를, 경험이 없는 분은 앞으로 필요한 정보를 선택해 주세요. ‘추가 정보가 필요하지 않음’은 단독 선택해 주세요.');
  mc_(form, 'U11. 현재 확보한 정보만으로 나에게 맞는 연구실을 선택할 수 있다고 얼마나 확신하나요?',
    ['1 전혀 확신하지 못함', '2 별로 확신하지 못함', '3 보통', '4 대체로 확신함', '5 매우 확신함', '판단할 정보가 없음']);
  form.addSectionHeaderItem().setTitle('검토 중인 커피챗 서비스').setHelpText(
    '관심 연구실의 대학원생과 1:1로 연결되어, 온라인에서 20분 동안 연구실 생활과 학부생의 연구참여 경험에 관해 질문할 수 있습니다. 다음 문항에서는 무료로 이용할 수 있다고 가정해 주세요.');
  mc_(form, 'U12. 향후 연구실을 선택할 때 이 대화를 이용할 의향은 어느 정도인가요?',
    ['1 전혀 없음', '2 별로 없음', '3 보통', '4 있음', '5 매우 있음']);
  mc_(form, 'U13. 이러한 대화를 이용할 때 가장 큰 걸림돌은 무엇인가요?',
    ['현재 연구참여 계획이나 정보 필요가 없음', '대화 상대의 정보가 솔직하고 정확할지 걱정됨',
     '대화 내용이 연구실에 전달되어 지원에 영향을 줄까 걱정됨',
     '질문을 준비하거나 처음 보는 사람과 대화하기 부담스러움', '시간·일정 조율이 어려움',
     '위 항목 외의 걸림돌', '특별한 걸림돌이 없음']);
  u1.setChoices([
    u1.createChoice('학부 1학년', pageB), u1.createChoice('학부 2학년', pageB),
    u1.createChoice('학부 3학년', pageB), u1.createChoice('학부 4학년 이상', pageB),
    u1.createChoice('현재 학부생이 아님', FormApp.PageNavigationType.SUBMIT)
  ]);
  u7.setChoices([
    u7.createChoice('1 매우 불만족', pageExperience), u7.createChoice('2 불만족', pageExperience),
    u7.createChoice('3 보통', pageExperience), u7.createChoice('4 만족', pageExperience),
    u7.createChoice('5 매우 만족', pageExperience), u7.createChoice('연구참여 경험이 없음', pageD)
  ]);
}

function buildGraduate_(form) {
  form.setTitle(graduateTitle_()).setDescription(graduateDescription_())
    .setConfirmationMessage('응답해 주셔서 감사합니다. 대학원생이 참여할 수 있는 커피챗 운영 조건을 설계하는 데 활용하겠습니다.');
  form.addSectionHeaderItem().setTitle('응답 대상');
  mc_(form, 'G1. 현재 재학 중인 과정은 무엇인가요?', ['석사', '박사', '통합']);
  section_(form, '참여 조건', graduateConditions_());
  const g2 = mc_(form, 'G2. 현재 소속 학과 또는 대학원 조직은 어디인가요?',
    graduateDepartments_(),
    '본인이 소속된 학과 또는 대학원 조직 하나를 선택해 주세요.');
  graduateDetail_(form, g2, 'G2-기타. 기타 소속 학과 또는 대학원 조직을 적어 주세요.', '기타');
  mc_(form, 'G3. 보상 여부와 별개로, 위 조건의 커피챗에 참여하는 것 자체에 얼마나 관심이 있나요?',
    ['1 전혀 관심 없음', '2 별로 관심 없음', '3 보통', '4 관심 있음', '5 매우 관심 있음']);
  mc_(form, 'G4. 다른 보상 없이 금전 보상만 제공된다면, 위 조건의 커피챗 1회에 참여할 최소 수령 금액은 얼마인가요?',
    ['0원 — 무보상으로도 참여 가능', '5,000원', '10,000원', '20,000원', '30,000원',
     '30,000원을 초과해야 참여 가능', '금액과 관계없이 참여 의향 없음'],
    '제시된 금액 중 참여할 수 있는 가장 낮은 금액을 선택해 주세요. 중간 금액이 필요하다면 그보다 높은 제시 금액을 선택해 주세요. 예: 최소 7,000원이 필요하다면 10,000원 선택.');
  const g5 = cb_(form, graduateRewardTitle_(), graduateRewards_(), graduateRewardHelp_());
  graduateDetail_(form, g5, 'G5-기타. 위 항목 외의 비금전 보상을 적어 주세요.', '위 항목 외의 비금전 보상');
  const g6 = cb_(form, 'G6. 커피챗을 통해 개인적으로 얻고 싶은 것은 무엇인가요? 최대 2개를 선택해 주세요.',
    ['내 경험이 학부생의 선택에 도움이 되는 것', '함께 연구할 관심 있는 학부생을 만나는 것',
     '설명·멘토링 능력을 기르는 것', '새로운 사람과의 교류와 관점 확장', '보상을 받는 것',
     '위 항목 외의 기대', '특별히 기대하는 것이 없음'],
    '‘특별히 기대하는 것이 없음’은 단독으로 선택해 주세요.');
  graduateDetail_(form, g6, 'G6-기타. 위 항목 외의 기대를 적어 주세요.', '위 항목 외의 기대');
  mc_(form, 'G7. 커피챗 1회의 실제 대화 시간으로 가장 적당한 것은 몇 분인가요? 준비 시간은 제외해 주세요.',
    ['10분', '20분', '30분', '45분', '60분 이상'],
    '선호 시간에 관한 질문입니다. 앞의 금액 질문은 동일한 20분 조건으로 답해 주세요.');
  mc_(form, 'G8. 시간과 보상 조건이 본인에게 맞는다면, 한 달에 몇 회까지 커피챗에 참여할 수 있나요?',
    ['0회 — 참여 불가', '1회', '2회', '3~4회', '5회 이상']);
  const g9 = mc_(form, 'G9. 커피챗 참여를 망설이게 하는 가장 큰 이유는 무엇인가요?',
    ['대화·준비에 쓸 시간이 부족함', '개인 의견이 연구실의 공식 입장으로 받아들여질까 걱정됨',
     '비공개 정보나 민감한 질문에 답하기 부담스러움', '처음 보는 학부생과 대화하기 부담스러움',
     '일정 조율·예약 취소 등 운영이 번거로울 것 같음', '위 항목 외의 이유', '특별히 망설이는 이유가 없음']);
  graduateDetail_(form, g9, 'G9-기타. 위 항목 외의 이유를 적어 주세요.', '위 항목 외의 이유');
}
