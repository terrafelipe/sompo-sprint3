// Gerado a partir do tailwind.config que ficava inline em templates/login.html.
// Rebuild: ver docs/COMO_TESTAR.md (Tailwind CLI standalone v3.4.17).
module.exports = {
  content: ['./templates/login.html'],
  ...({theme:{extend:{
      "colors":{
        "surface-tint":"#c00000","secondary":"#545f73","primary":"#b70100","surface":"#fff8f6",
        "background":"#fff8f6","on-primary":"#ffffff","on-surface":"#2a1613","on-background":"#2a1613",
        "on-surface-variant":"#5f3f3a","surface-variant":"#ffdad4","surface-container-lowest":"#ffffff",
        "surface-container-low":"#fff0ee","surface-container":"#ffe9e6","surface-container-high":"#ffe2dd",
        "primary-fixed-dim":"#ffb4a8","on-primary-fixed-variant":"#930100","outline":"#946e68",
        "outline-variant":"#e9bcb5","tertiary-container":"#0068f9","error":"#ba1a1a"
      },
      "borderRadius":{"DEFAULT":"0.25rem","lg":"0.5rem","xl":"0.75rem","full":"9999px"},
      "fontFamily":{"display-kpi":["Inter"],"body-md":["Inter"],"headline-lg":["Inter"],
        "headline-sm":["Inter"],"label-bold":["Inter"]},
      "fontSize":{
        "display-kpi":["48px",{"lineHeight":"1.1","letterSpacing":"-0.02em","fontWeight":"800"}],
        "headline-lg":["30px",{"lineHeight":"38px","fontWeight":"700"}],
        "headline-sm":["20px",{"lineHeight":"28px","fontWeight":"600"}],
        "body-md":["14px",{"lineHeight":"20px","fontWeight":"400"}],
        "label-bold":["12px",{"lineHeight":"16px","fontWeight":"700"}]
      }
    }}}),
};
