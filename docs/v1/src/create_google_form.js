/**
 * synco CEO WTP 검증 설문 v2 — Google Form 자동 생성 스크립트
 *
 * 사용법:
 * 1. https://script.google.com 접속
 * 2. 새 프로젝트 생성
 * 3. 이 코드 전체를 붙여넣기
 * 4. createSyncoWTPSurvey() 함수 실행
 * 5. 로그(Ctrl+Enter)에서 생성된 폼 URL 확인
 *
 * 주의: 컨셉 카드 이미지(synco 매칭 제안 화면)는 수동으로 삽입해야 합니다.
 *       스크립트 실행 후 폼 편집 화면에서 Section 6의 이미지 플레이스홀더를 실제 이미지로 교체하세요.
 */

function createSyncoWTPSurvey() {
  var form = FormApp.create('synco CEO WTP 검증 설문');
  form.setDescription(
    'AI가 귀사의 사업에 맞는 거래처를 자동으로 찾아주는 앱에 대한 의견을 듣고 싶습니다.\n\n' +
    '소요 시간: 약 8~10분\n' +
    '모든 응답은 익명으로 처리되며, 서비스 개발 목적으로만 활용됩니다.\n\n' +
    '설문 완료 시 스타벅스 기프티콘(5,000원)을 드립니다.'
  );
  form.setIsQuiz(false);
  form.setAllowResponseEdits(false);
  form.setCollectEmail(false);
  form.setLimitOneResponsePerUser(false);
  form.setProgressBar(true);
  form.setConfirmationMessage(
    '소중한 의견 감사합니다!\n\n' +
    '사전 등록하신 분께는 앱 출시 시 가장 먼저 알려드리겠습니다.\n' +
    '기프티콘은 영업일 기준 3일 이내에 발송됩니다.'
  );

  // ============================================================
  // Section 1. 기본 정보
  // ============================================================
  form.addSectionHeaderItem()
    .setTitle('Section 1. 기본 정보')
    .setHelpText('간단한 배경 정보를 여쭤봅니다. (약 1분)');

  // Q1
  form.addMultipleChoiceItem()
    .setTitle('Q1. 현재 역할을 선택해 주세요.')
    .setChoiceValues(['대표이사/CEO', '공동대표/파트너', '임원/C-level'])
    .showOtherOption(true)
    .setRequired(true);

  // Q2
  form.addMultipleChoiceItem()
    .setTitle('Q2. 회사의 주요 업종은?')
    .setChoiceValues([
      '제조/생산', '유통/물류', 'IT/소프트웨어',
      '서비스업 (컨설팅, 전문직 등)', '건설/부동산', '도소매/무역'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // Q3
  form.addMultipleChoiceItem()
    .setTitle('Q3. 연 매출 규모는?')
    .setChoiceValues([
      '10억 미만', '10~50억', '50~100억', '100~500억', '500억 이상'
    ])
    .setRequired(true);

  // Q4
  form.addMultipleChoiceItem()
    .setTitle('Q4. 직원 수는?')
    .setChoiceValues(['10명 미만', '10~50명', '50~100명', '100명 이상'])
    .setRequired(true);

  // ============================================================
  // Section 2. 인맥/거래처 관리 실태
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 2. 인맥/거래처 관리 실태')
    .setHelpText('현재 거래처·인맥을 어떻게 관리하고 계신지 여쭤봅니다. (약 2분)');

  // Q5
  form.addCheckboxItem()
    .setTitle('Q5. 비즈니스 거래처·파트너·인맥을 어떻게 관리하고 계세요? (복수 선택)')
    .setChoiceValues([
      '전화번호부/연락처 앱', '카카오톡 대화방/메모',
      '엑셀/스프레드시트', '명함 앱 (리멤버, 토스 명함 등)',
      'CRM 소프트웨어', '수첩/노트', '특별히 관리하지 않는다'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // Q6
  form.addScaleItem()
    .setTitle('Q6. 현재 거래처·인맥 관리 방식에 대한 만족도는?')
    .setBounds(1, 5)
    .setLabels('매우 불만', '매우 만족')
    .setRequired(true);

  // Q7
  form.addCheckboxItem()
    .setTitle('Q7. 거래처·인맥 관리에서 가장 불편한 점은? (최대 2개)')
    .setChoiceValues([
      '연락처가 여기저기 흩어져 있다',
      '누구를 언제 만났는지 기억이 안 난다',
      '거래처의 최근 사업 상황을 파악하기 어렵다',
      '오래된 거래처에 다시 연락하기 어렵다',
      '중요한 약속이나 팔로업을 놓친 적이 있다',
      '딱히 불편한 점 없다'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // ============================================================
  // Section 3. 메인 사업 거래 현황
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 3. 메인 사업 거래 현황')
    .setHelpText('귀사가 무엇을 팔고, 무엇이 필요한지 파악하기 위한 질문입니다. (약 2분)');

  // Q8 (카테고리 선택으로 변경)
  form.addMultipleChoiceItem()
    .setTitle('Q8. 귀사의 메인 사업(주력 제품/서비스) 분야는?')
    .setChoiceValues([
      '부품/소재 제조', '완제품 제조', '물류/운송',
      'IT/소프트웨어 개발', '전문 서비스 (컨설팅, 회계, 법률 등)',
      '도소매/유통', '건설/시공'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // Q8-1 (구체적 세부 — 선택)
  form.addTextItem()
    .setTitle('Q8-1. 구체적으로 어떤 제품/서비스인지 한 줄로 적어주세요. (선택)')
    .setHelpText('예: 자동차 부품 제조 / 물류 운송 서비스 / IT 솔루션 개발')
    .setRequired(false);

  // Q9
  form.addMultipleChoiceItem()
    .setTitle('Q9. 현재 새로운 공급처·제조사·생산 파트너가 필요하신가요?')
    .setChoiceValues([
      '예, 지금 당장 필요하다',
      '예, 조만간 필요할 것 같다',
      '현재는 필요 없다',
      '해당 없다'
    ])
    .setRequired(true);

  // Q10
  form.addMultipleChoiceItem()
    .setTitle('Q10. 현재 새로운 판매처·유통채널·납품처가 필요하신가요?')
    .setChoiceValues([
      '예, 지금 당장 필요하다',
      '예, 조만간 필요할 것 같다',
      '현재는 필요 없다',
      '해당 없다'
    ])
    .setRequired(true);

  // Q11
  form.addMultipleChoiceItem()
    .setTitle('Q11. 지금 새로운 거래처를 찾고 계신다면, 가장 큰 어려움은? (1개)')
    .setChoiceValues([
      '신뢰할 수 있는 거래처인지 판단이 어렵다',
      '내 업종·규모에 맞는 거래처 찾기가 어렵다',
      '처음 연락하는 것 자체가 어렵다',
      '탐색할 시간과 채널이 없다',
      '현재 거래처 탐색 필요 없다'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // ============================================================
  // Section 4. 사업 기회 탐색 현황
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 4. 사업 기회 탐색 현황')
    .setHelpText('새로운 거래처나 파트너를 어떻게 찾고 계신지 여쭤봅니다. (약 1분)');

  // Q12
  form.addCheckboxItem()
    .setTitle('Q12. 새로운 거래처나 사업 파트너를 주로 어떻게 찾으세요? (최대 2개)')
    .setChoiceValues([
      '지인/인맥 소개', '업종 모임/협회',
      '네트워킹 모임 (BNI 등)', '온라인 플랫폼 (리멤버, LinkedIn 등)',
      '전시회/박람회', '특별히 찾지 않는다'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // Q13
  form.addScaleItem()
    .setTitle('Q13. 현재 사업 기회 탐색 방법에 만족하세요?')
    .setBounds(1, 5)
    .setLabels('매우 불만', '매우 만족')
    .setRequired(true);

  // ============================================================
  // Section 5. 유휴 자원 현황 (통합 간소화)
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 5. 유휴 자원 현황')
    .setHelpText('메인 사업 외에 활용되지 않는 자원이 있는지 확인합니다. (약 1분)');

  // Q14 (Q14+Q15 통합)
  form.addCheckboxItem()
    .setTitle('Q14. 귀사에 현재 충분히 활용되지 않는 자원이 있고, 이를 통해 추가 수익을 내고 싶으신가요? (복수 선택)')
    .setChoiceValues([
      '설비/장비 여유가 있고, 활용하고 싶다',
      '재고/원자재 여유가 있다',
      '유통채널/영업망을 더 활용할 수 있다',
      '공간(사무실/창고) 여유가 있다',
      '기술/특허를 라이선스하고 싶다',
      '유휴 자원이 없다',
      '유휴 자원은 있지만 활용 관심 없다'
    ])
    .setRequired(true);

  // ============================================================
  // Section 6. 솔루션 컨셉 제시 + 반응
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 6. 새로운 서비스를 소개합니다')
    .setHelpText('아래 서비스 컨셉을 읽고 의견을 들려주세요. (약 3분)');

  // 컨셉 카드 (이미지 삽입 안내 포함)
  form.addSectionHeaderItem()
    .setTitle('AI B2B 매칭 앱 — synco')
    .setHelpText(
      '[ 아래에 매칭 제안 샘플 이미지를 삽입하세요 ]\n\n' +
      'synco는 이렇게 작동합니다:\n\n' +
      '① 메인 사업 거래처 매칭 (핵심)\n' +
      'AI가 귀사의 주력 사업과 실제로 거래 가능한 기업을 찾아드립니다.\n' +
      '"귀사 제품을 구매할 바이어", "귀사가 필요한 공급사", "협력 가능한 파트너"를 AI가 발굴합니다.\n' +
      '매칭 확률, 업종 적합도, 예상 시너지를 한눈에 보여드립니다.\n\n' +
      '② 유휴 자원 활용 (보너스 옵션)\n' +
      '메인 사업 매칭에 더해, 유휴 설비·재고·공간까지 활용할 수 있는 기회를 추가로 제안합니다.\n\n' +
      '③ AI 인맥 관리 & 브리핑\n' +
      '거래처 연락처를 한 곳에서 관리하고, 미팅 전 상대방의 최근 사업 현황을 AI가 자동 브리핑합니다.\n\n' +
      '④ 신뢰 기반 연결\n' +
      'AI가 매칭을 발견하고, 양측 대표를 모두 아는 전문 비즈니스 어드바이저가 실제 거래로 연결합니다.\n' +
      '처음 보는 사람끼리 연결하는 것이 아니라, 이미 관계가 있는 사람이 소개해드립니다.\n\n' +
      '인맥/일정 관리, 메인 사업 등록은 무료.\n' +
      '매칭 상세 정보 열람 및 직접 연결은 유료입니다.'
    );

  // Q16
  form.addScaleItem()
    .setTitle('Q16. 이 앱에 대한 전반적인 관심도는?')
    .setBounds(1, 5)
    .setLabels('전혀 관심 없다', '지금 당장 써보고 싶다')
    .setRequired(true);

  // Q17
  form.addMultipleChoiceItem()
    .setTitle('Q17. 가장 매력적인 기능은? (1개)')
    .setChoiceValues([
      'AI가 메인 사업 거래처를 자동으로 찾아줌',
      '유휴 자원 활용 기회 발굴',
      '메인 사업 + 유휴 자원 통합 매칭 (관계 점수 최고)',
      'AI 미팅 브리핑 (거래처 사업 현황 자동 요약)',
      '인맥/거래처 통합 관리',
      '매력적인 기능이 없다'
    ])
    .setRequired(true);

  // Q17-1 (신규: 소개 vs 직접 연락 선호)
  form.addMultipleChoiceItem()
    .setTitle('Q17-1. 새로운 거래처와 연결될 때, 어떤 방식을 더 선호하세요?')
    .setChoiceValues([
      'AI가 추천한 기업에 직접 연락한다 (플랫폼 메시지/전화)',
      '양측을 모두 아는 사람이 소개해준다',
      '두 방식 모두 괜찮다',
      '상황에 따라 다르다'
    ])
    .setRequired(true);

  // Q18
  form.addMultipleChoiceItem()
    .setTitle('Q18. 가장 먼저 쓰고 싶은 기능은? (1개)')
    .setChoiceValues([
      '메인 사업 거래처 매칭 (바이어·공급사 발굴)',
      '인맥/거래처 관리 (흩어진 연락처 정리)',
      'AI 브리핑 (미팅 전 상대방 정보 자동 요약)',
      '유휴 자원 활용 매칭',
      '딱히 없다'
    ])
    .setRequired(true);

  // Q19
  form.addCheckboxItem()
    .setTitle('Q19. 이 앱을 쓸 때 가장 걱정되는 점은? (최대 2개)')
    .setChoiceValues([
      '매칭 품질이 낮을 것 같다',
      '내 사업 정보가 경쟁사에 노출될까 걱정',
      'AI를 신뢰하기 어렵다',
      '앱 하나 더 깔기 귀찮다',
      '비용 부담',
      '실제 거래까지 이어질지 의문',
      '걱정 없다'
    ])
    .showOtherOption(true)
    .setRequired(true);

  // ============================================================
  // Section 7. WTP (지불 의향)
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 7. 가격에 대한 의견')
    .setHelpText('이 서비스의 적정 가격에 대한 의견을 들려주세요. 가장 중요한 섹션입니다. (약 3분)');

  // 시나리오 A 설명
  form.addSectionHeaderItem()
    .setTitle('시나리오 A: 건당 크레딧')
    .setHelpText(
      'AI가 "귀사 메인 사업과 실제 거래 가능한 기업"을 발견했습니다.\n' +
      '요약(업종, 예상 시너지, 거래 유형)은 무료로 볼 수 있고,\n' +
      '기업명, 대표 프로필, 구체적 거래 시나리오를 보려면 크레딧이 필요합니다.'
    );

  // Q20
  form.addMultipleChoiceItem()
    .setTitle('Q20. 이런 매칭 정보 1건의 상세 열람에 적정한 가격은?')
    .setChoiceValues([
      '무료여야 한다',
      '1,000~3,000원',
      '3,000~5,000원',
      '5,000~10,000원',
      '10,000원 이상도 괜찮다',
      '가격과 무관하게 관심 없다'
    ])
    .setRequired(true);

  // Q21
  form.addMultipleChoiceItem()
    .setTitle('Q21. 한 달에 이런 매칭 정보를 몇 건 정도 보시겠어요?')
    .setChoiceValues(['0건', '1~3건', '4~10건', '10건 이상'])
    .setRequired(true);

  // 시나리오 B 설명
  form.addSectionHeaderItem()
    .setTitle('시나리오 B: 월 구독')
    .setHelpText(
      '월 구독 시: 매칭 정보 무제한 열람 + AI 브리핑 + 우선 연결이 포함됩니다.\n\n' +
      '아래 4개 질문은 적정 가격을 파악하기 위한 것입니다. 직감적으로 느끼는 금액을 숫자로만 적어주세요.'
    );

  // Q22
  form.addTextItem()
    .setTitle('Q22. 이 서비스의 월 구독료로 "싸다"고 느껴지는 금액은? (숫자만 입력, 원/월)')
    .setHelpText('예: 30000')
    .setRequired(true);

  // Q23
  form.addTextItem()
    .setTitle('Q23. "적절하다"고 느껴지는 금액은? (숫자만 입력, 원/월)')
    .setHelpText('예: 50000')
    .setRequired(true);

  // Q24
  form.addTextItem()
    .setTitle('Q24. "비싸다, 고민된다"고 느껴지는 금액은? (숫자만 입력, 원/월)')
    .setHelpText('예: 100000')
    .setRequired(true);

  // Q25
  form.addTextItem()
    .setTitle('Q25. "이 가격이면 절대 안 쓴다"고 느껴지는 금액은? (숫자만 입력, 원/월)')
    .setHelpText('예: 200000')
    .setRequired(true);

  // 시나리오 C 설명
  form.addSectionHeaderItem()
    .setTitle('시나리오 C: 성과 기반')
    .setHelpText('매칭으로 실제 거래가 성사됐을 때만 수수료를 내는 모델입니다.');

  // Q26
  form.addMultipleChoiceItem()
    .setTitle('Q26. 매칭으로 실제 거래가 성사됐을 때, 거래 금액의 일정 비율을 수수료로 내는 모델은?')
    .setChoiceValues([
      '합리적이다 — 성과 있을 때만 내니까',
      '거래 규모에 따라 다르다',
      '수수료 모델은 싫다',
      '관심 없다'
    ])
    .setRequired(true);

  // Q27 (조건부이지만 구글 폼에서는 모두에게 보여줌 — 해당 없음 옵션 추가)
  form.addMultipleChoiceItem()
    .setTitle('Q27. (수수료 모델에 관심 있다면) 적정 수수료율은?')
    .setChoiceValues([
      '1~2%', '3~5%', '5~10%',
      '소액 거래 높게, 대액 거래 낮게',
      '해당 없음 (Q26에서 "싫다" 또는 "관심 없다" 선택)'
    ])
    .setRequired(true);

  // 과금 모델 선호
  form.addSectionHeaderItem()
    .setTitle('과금 모델 선호');

  // Q28
  form.addMultipleChoiceItem()
    .setTitle('Q28. 세 가지 과금 방식 중 가장 선호하는 것은?')
    .setChoiceValues([
      '건당 크레딧 (필요할 때만 결제)',
      '월 구독 (정기 결제, 무제한)',
      '성과 기반 (거래 성사 시만 수수료)',
      '무료 아니면 안 쓴다'
    ])
    .setRequired(true);

  // ============================================================
  // Section 8. 행동 신호 (Commitment Ladder)
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 8. 마지막 질문')
    .setHelpText('거의 다 왔습니다! 마지막 질문 몇 개만 답해주세요. (약 1분)');

  // Q29
  form.addMultipleChoiceItem()
    .setTitle('Q29. 이 앱이 출시된다면?')
    .setChoiceValues([
      '관심 없다',
      '무료 기능만 쓰겠다',
      '무료로 써보고, 괜찮으면 유료도 고려하겠다',
      '바로 유료로 시작하겠다'
    ])
    .setRequired(true);

  // Q30 (사전 등록 — 핵심 행동 지표)
  form.addMultipleChoiceItem()
    .setTitle('Q30. 지금 바로 사전 등록(출시 시 알림)을 하시겠습니까?')
    .setChoiceValues(['예', '아니오'])
    .setRequired(true);

  // Q30-1 (연락처 — 사전 등록 시)
  form.addTextItem()
    .setTitle('Q30-1. (사전 등록 시) 연락받으실 전화번호 또는 이메일을 남겨주세요.')
    .setHelpText('출시 시 가장 먼저 알려드립니다. 사전 등록하지 않으시면 빈칸으로 두세요.')
    .setRequired(false);

  // Q31
  form.addMultipleChoiceItem()
    .setTitle('Q31. 주변에 이 앱에 관심 가질 대표님이 계세요?')
    .setChoiceValues([
      '5명 이상 떠오른다',
      '1~4명 떠오른다',
      '없다'
    ])
    .setRequired(true);

  // ============================================================
  // Section 9. 개방형 (선택)
  // ============================================================
  form.addPageBreakItem()
    .setTitle('Section 9. 자유 의견 (선택)')
    .setHelpText('추가로 하고 싶은 말씀이 있으시면 자유롭게 적어주세요.');

  // Q32
  form.addParagraphTextItem()
    .setTitle('Q32. 이 앱에 추가로 있으면 좋겠다 싶은 기능이 있으세요?')
    .setRequired(false);

  // Q33
  form.addParagraphTextItem()
    .setTitle('Q33. 이 앱을 안 쓸 것 같다면, 가장 큰 이유는?')
    .setRequired(false);

  // ============================================================
  // 완료
  // ============================================================
  var publishedUrl = form.getPublishedUrl();
  var editUrl = form.getEditUrl();

  Logger.log('=== synco CEO WTP 설문 생성 완료 ===');
  Logger.log('응답 URL: ' + publishedUrl);
  Logger.log('편집 URL: ' + editUrl);
  Logger.log('');
  Logger.log('다음 단계:');
  Logger.log('1. 편집 URL에서 Section 6의 컨셉 카드에 매칭 제안 와이어프레임 이미지를 삽입하세요.');
  Logger.log('2. 설문을 미리보기로 확인하세요.');
  Logger.log('3. 응답 스프레드시트를 연결하세요 (응답 탭 → 스프레드시트 아이콘).');

  return { publishedUrl: publishedUrl, editUrl: editUrl };
}
