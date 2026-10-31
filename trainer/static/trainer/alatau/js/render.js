'use strict';
/* ---------------- Рендер ---------------- */
let renderer, scene, camera, rt, postScene, postCam, postMat, world = null, sky, sun, hemi, bars, playerAvatar;
const LOOKS = {
  bodycam: { fov: 98, dist: .62, ca: .012, grain: .085, vig: .75, exp: 1.06, sat: .74, con: 1.2, tint: [.95, 1.02, 1.0], mono: 0, blur: 1, sway: 1, h: 1.36 },
  clean: { fov: 72, dist: 0, ca: 0, grain: 0, vig: .2, exp: 1.0, sat: 1.06, con: 1.03, tint: [1, 1, 1], mono: 0, blur: .25, sway: .35, h: 1.62 },
  film: { fov: 68, dist: .12, ca: .003, grain: .06, vig: .55, exp: 1.04, sat: .86, con: 1.1, tint: [1.06, 1.0, .88], mono: 0, blur: .3, sway: .5, h: 1.55 },
  noir: { fov: 80, dist: .3, ca: .002, grain: .13, vig: .85, exp: 1.08, sat: 1, con: 1.35, tint: [1, 1, 1], mono: 1, blur: .3, sway: .7, h: 1.45 }
};
const look = Object.assign({}, LOOKS.bodycam);

function initGL() {
  const canvas = $('#gl');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, logarithmicDepthBuffer: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(90, 1, .15, 120000);
  scene.add(camera);
  const sunDir = new THREE.Vector3(-.55, .48, .38).normalize();
  sun = new THREE.DirectionalLight(0xfff0d8, .95); sun.position.copy(sunDir); scene.add(sun);
  hemi = new THREE.HemisphereLight(0xd6e6ff, 0x5b5242, .72); scene.add(hemi);
  scene.fog = new THREE.FogExp2(0xbfd2e3, .000042);
  sky = new THREE.Mesh(new THREE.SphereGeometry(1000, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, depthTest: false, fog: false,
    uniforms: { top: { value: new THREE.Color(0x3f78b8) }, hor: { value: new THREE.Color(0xc6d8e8) }, bot: { value: new THREE.Color(0x8f9aa0) }, sunDir: { value: sunDir } },
    vertexShader: 'varying vec3 vD; void main(){ vD=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); gl_Position.z=gl_Position.w*0.9999; }',
    fragmentShader: 'uniform vec3 top,hor,bot,sunDir; varying vec3 vD; void main(){ vec3 d=normalize(vD); float h=d.y; vec3 c=mix(hor,top,pow(clamp(h,0.,1.),.55)); c=mix(c,bot,clamp(-h*5.,0.,1.)); float s=max(dot(d,normalize(sunDir)),0.); c+=vec3(1.,.86,.62)*(pow(s,900.)*3.5+pow(s,10.)*.22); gl_FragColor=vec4(c,1.); }'
  }));
  sky.renderOrder = -10; sky.frustumCulled = false; scene.add(sky);

  // Руль и руки в кадре (камера на груди, как у бодикамеры)
  bars = makeBars(); camera.add(bars);
  setPlayerChar(settings.char);

  postScene = new THREE.Scene(); postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  postMat = new THREE.ShaderMaterial({
    uniforms: { tD: { value: null }, uRes: { value: new THREE.Vector2(1, 1) }, uTime: { value: 0 }, uDist: { value: 0 }, uCA: { value: 0 }, uGrain: { value: 0 }, uVig: { value: 0 }, uBlur: { value: 0 }, uExp: { value: 1 }, uSat: { value: 1 }, uCon: { value: 1 }, uTint: { value: new THREE.Vector3(1, 1, 1) }, uMono: { value: 0 } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position.xy,0.,1.); }',
    fragmentShader: [
      'precision highp float;',
      'uniform sampler2D tD; uniform vec2 uRes; uniform float uTime,uDist,uCA,uGrain,uVig,uBlur,uExp,uSat,uCon,uMono; uniform vec3 uTint; varying vec2 vUv;',
      'float hash(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y); }',
      'vec2 warp(vec2 uv){ float a=uRes.x/uRes.y; vec2 c=uv-.5; c.x*=a; float r2=dot(c,c); float rm=.25*(a*a+1.); c*=(1.+uDist*r2)/(1.+uDist*rm); c.x/=a; return c+.5; }',
      'vec3 samp(vec2 uv){ vec2 c=uv-.5; return vec3(texture2D(tD,uv+c*uCA).r, texture2D(tD,uv).g, texture2D(tD,uv-c*uCA).b); }',
      'void main(){ vec2 uv=warp(vUv); vec2 c=uv-.5; vec3 col=samp(uv);',
      ' if(uBlur>0.0005){ vec3 acc=col; for(int i=1;i<8;i++){ float t=float(i)/8.; acc+=samp(uv-c*uBlur*t); } col=acc/8.; }',
      ' col*=uExp; float l=dot(col,vec3(.2126,.7152,.0722)); col=mix(vec3(l),col,uSat); col=(col-.5)*uCon+.5; col*=uTint;',
      ' col=mix(col,vec3(dot(col,vec3(.299,.587,.114))),uMono);',
      ' float v=smoothstep(.9,.22,length(vUv-.5)*1.3); col*=mix(1.,v,uVig);',
      ' col+= (hash(vUv*uRes+fract(uTime*7.13)*97.)-.5)*uGrain;',
      ' gl_FragColor=vec4(clamp(col,0.,1.),1.); }'
    ].join('\n'), depthTest: false, depthWrite: false
  });
  postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMat));
  onResize(); window.addEventListener('resize', onResize);
}
function onResize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h; camera.updateProjectionMatrix();
  const v = new THREE.Vector2(); renderer.getDrawingBufferSize(v);
  if (rt) rt.dispose();
  const opts = { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter };
  rt = (renderer.capabilities.isWebGL2 && THREE.WebGLMultisampleRenderTarget) ? new THREE.WebGLMultisampleRenderTarget(v.x, v.y, opts) : new THREE.WebGLRenderTarget(v.x, v.y, opts);
  postMat.uniforms.uRes.value.set(v.x, v.y);
  bars.position.set(0, -.36 - (w < h ? .04 : 0), -.5);
  drawProfileBase();
}

function canvasTex(w, h, draw) { const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.anisotropy = renderer.capabilities.getMaxAnisotropy(); return t; }
function roadTexture(lanes) {
  return canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = '#3a3c3f'; g.fillRect(0, 0, w, h);
    const r = rng(7); for (let i = 0; i < 2600; i++) { const c = 40 + r() * 40 | 0; g.fillStyle = 'rgba(' + c + ',' + c + ',' + (c + 3) + ',.55)'; g.fillRect(r() * w, r() * h, 1 + r() * 2, 1 + r() * 2); }
    g.fillStyle = 'rgba(0,0,0,.18)'; g.fillRect(w * .18, 0, w * .1, h); g.fillRect(w * .72, 0, w * .1, h);
    g.fillStyle = '#e9e9e2'; g.fillRect(4, 0, 4, h); g.fillRect(w - 8, 0, 4, h);
    if (lanes >= 4) { g.fillRect(w / 2 - 5, 0, 3, h); g.fillRect(w / 2 + 2, 0, 3, h); } else { g.fillRect(w / 2 - 2, 0, 4, h * .45); }
    const per = lanes / 2;
    for (let k = 1; k < per; k++) { const x1 = w / 2 * k / per, x2 = w - x1; g.fillRect(x1 - 2, 0, 4, h * .4); g.fillRect(x2 - 2, 0, 4, h * .4); }
  });
}
let buildingMat, treeMat, osmMat;
function makeMaterials() {
  buildingMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
  const winShader = sh => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec3 vWN;')
      .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\n#ifdef USE_INSTANCING\n mat4 wm=modelMatrix*instanceMatrix;\n#else\n mat4 wm=modelMatrix;\n#endif\n vWP=(wm*vec4(transformed,1.0)).xyz; vWN=normalize(mat3(wm)*objectNormal);');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec3 vWN;')
      .replace('#include <color_fragment>', '#include <color_fragment>\n if(abs(vWN.y)<0.5){ vec2 t=normalize(vec2(-vWN.z,vWN.x)); float u=dot(vWP.xz,t); float fl=fract(vWP.y/3.0); float cl=fract(u/3.3); float win=step(.2,fl)*step(fl,.7)*step(.18,cl)*step(cl,.74); float lit=step(.86,fract(sin(dot(floor(vec2(u/3.3,vWP.y/3.0)),vec2(12.9898,78.233)))*43758.5453)); vec3 glass=mix(vec3(.15,.19,.24),vec3(.62,.66,.66),lit*.6); diffuseColor.rgb=mix(diffuseColor.rgb,glass,win*.88); } else { diffuseColor.rgb*=.7; }');
  };
  buildingMat.onBeforeCompile = winShader;
  osmMat = new THREE.MeshLambertMaterial({ vertexColors: true }); osmMat.onBeforeCompile = winShader;
  treeMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
}
function makeBars() {
  const g = new THREE.Group();
  const dark = new THREE.MeshStandardMaterial({ color: 0x1b1d20, roughness: .55, metalness: .3 });
  const tape = new THREE.MeshStandardMaterial({ color: 0x2a2c30, roughness: .9 });
  const glove = new THREE.MeshStandardMaterial({ color: 0x3a3f46, roughness: .85 });
  const top = new THREE.Mesh(new THREE.CylinderGeometry(.013, .013, .42, 10), tape); top.rotation.z = Math.PI / 2; g.add(top);
  [-1, 1].forEach(s => {
    const drop = new THREE.Mesh(new THREE.TorusGeometry(.07, .012, 8, 16, Math.PI * 1.15), tape);
    drop.rotation.y = Math.PI / 2; drop.rotation.z = -Math.PI / 2; drop.position.set(s * .21, -.07, -.03); g.add(drop);
    const hood = new THREE.Mesh(new THREE.BoxGeometry(.03, .045, .07), dark); hood.position.set(s * .21, .005, -.075); hood.rotation.x = -.35; g.add(hood);
    const hand = new THREE.Mesh(new THREE.SphereGeometry(.045, 12, 10), glove); hand.scale.set(1, .8, 1.35); hand.position.set(s * .2, .015, -.04); g.add(hand);
  });
  const stem = new THREE.Mesh(new THREE.BoxGeometry(.035, .035, .12), dark); stem.position.set(0, -.012, .05); stem.rotation.x = -.15; g.add(stem);
  const unit = new THREE.Mesh(new THREE.BoxGeometry(.055, .012, .085), dark); unit.position.set(0, .02, -.06); g.add(unit);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(.045, .07), new THREE.MeshBasicMaterial({ color: 0x9fb8a8 })); scr.rotation.x = -Math.PI / 2; scr.position.set(0, .027, -.06); g.add(scr);
  const tire = new THREE.Mesh(new THREE.TorusGeometry(.34, .016, 8, 40, Math.PI * .5), new THREE.MeshStandardMaterial({ color: 0x151515, roughness: .9 }));
  tire.rotation.y = Math.PI / 2; tire.rotation.z = Math.PI * .25; tire.position.set(0, -.52, -.42); g.add(tire);
  g.traverse(o => { o.renderOrder = 5; });
  return g;
}
