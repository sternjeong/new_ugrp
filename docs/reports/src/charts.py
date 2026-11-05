import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
fm.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
fm.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK KR','axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,
  'axes.edgecolor':'#9a9a96','axes.labelcolor':'#52514e','xtick.color':'#52514e','ytick.color':'#52514e','figure.facecolor':'#ffffff','axes.facecolor':'#ffffff','font.size':10})
C=['#2a78d6','#eb6834','#1baf7a','#eda100']; INK='#0b0b0b'; MUTE='#52514e'
def bars(ax, groups, series, colors, labels, ylim, fmt='{:.2f}'):
    n=len(series); w=0.8/n
    for i,(s,c,l) in enumerate(zip(series,colors,labels)):
        xs=[g+(i-(n-1)/2)*w for g in range(len(groups))]
        b=ax.bar(xs,s,w*0.88,color=c,label=l)
        for x,v in zip(xs,s): ax.text(x,v+ylim*0.015,fmt.format(v),ha='center',va='bottom',fontsize=(6.5 if n>=4 else 8),color=INK)
    ax.set_xticks(range(len(groups))); ax.set_xticklabels(groups); ax.set_ylim(0,ylim)
    ax.yaxis.grid(True,color='#e6e5e0',lw=0.8); ax.set_axisbelow(True)
# 1. bge-m3 v2: 관련도 평균 (A-E)와 v3 (A,E,F,G,H)
fig,ax=plt.subplots(1,2,figsize=(9.2,3.3))
bars(ax[0],['A','B','C','D','E'],[[0.88,0.89,0.82,0.76,0.87]],[C[0]],['평균 관련도'],1.3)
ax[0].set_title('v2: 상위 10개 평균 관련도 (0~2)',fontsize=10,loc='left',color=INK)
ax[1].bar(range(5),[0.88,0.87,0.95,1.05,1.05],0.6,color=[C[0],C[0],C[0],C[1],C[1]])
for x,v in zip(range(5),[0.88,0.87,0.95,1.05,1.05]): ax[1].text(x,v+0.02,f'{v:.2f}',ha='center',fontsize=8)
ax[1].set_xticks(range(5)); ax[1].set_xticklabels(['A','E','F','G','H']); ax[1].set_ylim(0,1.3); ax[1].yaxis.grid(True,color='#e6e5e0',lw=0.8); ax[1].set_axisbelow(True)
ax[1].set_title('v3: 규칙 가산 비중을 올린 G·H가 처음으로 개선',fontsize=10,loc='left',color=INK)
plt.tight_layout(); plt.savefig('img/bge_v2v3.png',dpi=200); plt.close()
# 2. bge v4: 상위 3/5/10 평균 + 0점 비율
fig,ax=plt.subplots(1,2,figsize=(9.2,3.3))
bars(ax[0],['상위 3개','상위 5개','상위 10개'],[[1.25,1.12,0.88],[1.43,1.23,1.05],[1.50,1.30,1.00],[1.50,1.35,1.05]],C,['A','H','R1 재순위','R2 재순위+규칙'],1.9)
ax[0].set_title('평균 관련도 (0~2, 높을수록 좋음)',fontsize=10,loc='left',color=INK); ax[0].legend(frameon=False,fontsize=8,loc='upper right',ncol=2)
bars(ax[1],['상위 3개','상위 5개','상위 10개'],[[22,27,40],[13,23,28],[7,15,30],[7,14,26]],C,['A','H','R1','R2'],50,fmt='{:.0f}%')
ax[1].set_title('무관(0점) 비율 % (낮을수록 좋음)',fontsize=10,loc='left',color=INK)
plt.tight_layout(); plt.savefig('img/bge_v4.png',dpi=200); plt.close()
# 3. reason engine v3
fig,ax=plt.subplots(1,2,figsize=(9.2,3.3))
names=['M2 근거 인용','M4b LLM 자유','M5b LLM+단어검사','M7 템플릿+명사구','M8 M7+NLI']
bad=[0,44,13,4,2]
ax[0].barh(range(5),bad,0.6,color=[C[0],C[1],C[0],C[2],C[2]]); ax[0].invert_yaxis()
for y,v in enumerate(bad): ax[0].text(v+0.8,y,f'{v}/60',va='center',fontsize=8)
ax[0].set_yticks(range(5)); ax[0].set_yticklabels(names,fontsize=8.5); ax[0].set_xlim(0,52); ax[0].xaxis.grid(True,color='#e6e5e0',lw=0.8); ax[0].set_axisbelow(True)
ax[0].set_title('v3: 근거에 없는 내용을 말한 문장 (건/60)',fontsize=10,loc='left',color=INK)
bars(ax[1],['정확','구체','자연','도움'],[[1.00,1.68/3,1.88/3,1.45/3],[0.27,1.73/3,2.70/3,1.47/3],[0.93,1.78/3,2.60/3,1.63/3]],[C[0],C[1],C[2]],['M2','M4b','M7'],1.25)
ax[1].set_title('v3 채점 (모두 0~1로 환산: 정확은 0/1, 나머지는 1~3점÷3)',fontsize=9,loc='left',color=INK); ax[1].legend(frameon=False,fontsize=8,ncol=3,loc='upper center')
plt.tight_layout(); plt.savefig('img/reason_v3.png',dpi=200); plt.close()
# 4. A/B 평가
fig,ax=plt.subplots(figsize=(9.2,3.2))
bars(ax,['1 상위 적합성','2 무관 과목 없음','6 사실 정확성','7 구체성','8 납득도'],[[3.50,3.35,3.75,1.30,1.95],[3.95,3.50,3.10,3.15,2.90]],[C[0],C[1]],['A 현재 앱','B 새 엔진 (R2 + M8)'],5.2)
ax.set_title('블라인드 A/B 평가 (페르소나 5명, 20건, 1~5점) — 정확성만 A가 높음',fontsize=10,loc='left',color=INK); ax.legend(frameon=False,fontsize=9,ncol=2,loc='upper right')
plt.tight_layout(); plt.savefig('img/ab.png',dpi=200); plt.close()
# 5. QU v1 (P@5)
fig,ax=plt.subplots(1,2,figsize=(9.2,3.4))
bars(ax[0],['단순','다른 표현','복합 용어','다중 관심','전체'],[[1.00,0.53,0.66,0.83,0.69],[0.53,0.55,0.49,0.50,0.47],[0.77,0.62,0.51,0.77,0.66],[1.00,0.72,0.71,0.90,0.84]],C,['A 현재 앱','B 문장 전체 임베딩','C 규칙해석+임베딩','사전+해석+임베딩 융합'],1.35)
ax[0].set_title('v1 (개발 질의 39개): 상위 5개 정답 비율',fontsize=10,loc='left',color=INK); ax[0].legend(frameon=False,fontsize=7.5,ncol=2,loc='upper right')
bars(ax[1],['A 현재 앱','B 임베딩만','C 규칙+임베딩','사전+해석'],[[75,75,8,17]],[C[1]],['혼입'],100,fmt='{:.0f}%')
ax[1].set_title('싫다고 한 주제가 상위 5개에 섞인 질의 %',fontsize=10,loc='left',color=INK)
plt.tight_layout(); plt.savefig('img/qu_v1.png',dpi=200); plt.close()
# 6. QU v2
fig,ax=plt.subplots(1,2,figsize=(9.2,3.4))
bars(ax[0],['사전 지표','보정 지표'],[[0.51,0.62],[0.60,0.74],[0.68,0.81]],[C[0],C[2],C[1]],['A 현재 앱','사전+해석 (임베딩 없음)','제안 파이프라인'],1.05)
ax[0].set_title('v2 시험 질의 68개: 성공률 (제안은 라우팅 무시)',fontsize=10,loc='left',color=INK); ax[0].legend(frameon=False,fontsize=8,loc='upper left',ncol=1)
bars(ax[1],['A 현재 앱','제안'],[[26,9]],[C[1]],['조용한 실패'],34,fmt='{:.0f}')
ax[1].set_title('조용한 실패: 틀렸는데 아무 표시 없는 질의 (/68, 보정 지표)',fontsize=9,loc='left',color=INK)
plt.tight_layout(); plt.savefig('img/qu_v2.png',dpi=200); plt.close()
print('ok')
