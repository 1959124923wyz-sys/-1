(() => {
  'use strict';

  function create({
    map, getStateGeo, getStatePanel, tooltipHtml, onChange,
  }) {
    let layer = null;

    function style(feature) {
      const selected = feature?.properties?.name === getStatePanel()?.selectedName;
      return {
        pane:'statePane',color:selected?'#ffffff':'#20384b',
        weight:selected?3.1:2,opacity:selected?1:.98,
        fillColor:'#dce7ee',fillOpacity:selected?.045:.006,
      };
    }

    function render() {
      if (layer) { map.removeLayer(layer); layer = null; }
      const geo = getStateGeo();
      if (!geo || map.getZoom() >= 7.5) return null;
      const interactive = map.getZoom() <= 7.15;
      layer = L.geoJSON(geo,{
        pane:'statePane',style,interactive,
        onEachFeature:(feature,target)=>{
          if (!interactive) return;
          target.bindTooltip(()=>tooltipHtml(feature),{sticky:true,direction:'top',className:'state-tip'});
          target.on('mouseover',()=>{
            if(feature.properties?.name!==getStatePanel()?.selectedName)
              target.setStyle({color:'#f4fbff',weight:2.65,fillOpacity:.055});
          });
          target.on('mouseout',()=>layer?.resetStyle(target));
          target.on('click',()=>{
            getStatePanel().select(feature);
            layer.eachLayer(item=>layer.resetStyle(item));
            target.setStyle(style(feature));
            onChange?.(feature);
            if(target.getBounds)map.fitBounds(target.getBounds(),{padding:[32,32],maxZoom:7.05});
          });
        }
      }).addTo(map);
      return layer;
    }

    return Object.freeze({render,style,get layer(){return layer;}});
  }

  window.CrimeStateLayer=Object.freeze({create});
})();
