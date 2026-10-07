(() => {
  const propertyMetrics = Object.freeze({
    property_total: { label: '盗窃总体', de: 'Diebstahl insgesamt' },
    burglary: { label: '入室盗窃', de: 'Wohnungseinbruchdiebstahl' },
    bicycle_theft: { label: '自行车盗窃', de: 'Fahrraddiebstahl' },
    vehicle_theft: { label: '机动车盗窃', de: 'Diebstahl von Kraftwagen' },
    theft_from_vehicle: { label: '车内/车上盗窃', de: 'Diebstahl an/aus Kraftfahrzeugen' },
  });

  const violenceMetrics = Object.freeze({
    violence: {
      label: '暴力总体',
      de: 'Gewaltkriminalität',
      news: ['homicide', 'violence', 'robbery', 'sexual'],
    },
    serious_injury: {
      label: '严重伤害',
      de: 'Gefährliche und schwere Körperverletzung',
      news: ['violence'],
    },
    robbery: { label: '抢劫', de: 'Raub', news: ['robbery'] },
    sexual: {
      label: '性犯罪',
      de: 'Vergewaltigung und sexuelle Übergriffe',
      news: ['sexual'],
    },
    homicide: { label: '凶杀', de: 'Mord und Totschlag', news: ['homicide'] },
  });

  window.CrimeMapConfig = Object.freeze({
    NATIONAL_VIOLENCE_2025: 212335,
    categories: Object.freeze({
      homicide: { label: '凶杀', color: '#d6534f' },
      violence: { label: '严重暴力', color: '#df8a45' },
      robbery: { label: '抢劫', color: '#4f95bd' },
      sexual: { label: '性犯罪', color: '#9e76c8' },
      property: { label: '盗窃/财产', color: '#5a82d3' },
    }),
    palettes: Object.freeze({
      national: ['#fff4e6','#fee2c2','#fbc48d','#f59e5b','#ea7449','#d94b3d','#ad2e32'],
      berlin: ['#f5effa','#e6d7f2','#d2b7e5','#bb92d5','#9c68c1','#7c47a6','#5d2d83'],
      property: ['#eff6ff','#d9eafb','#b9d8f3','#8bbce3','#5a9bd2','#3678b8','#1f4f8f'],
      berlinProperty: ['#edf4ff','#d5e6fb','#b8d3f2','#8eb8e4','#629bd2','#3e78b7','#24528f'],
    }),
    propertyMetrics,
    violenceMetrics,
  });
})();
