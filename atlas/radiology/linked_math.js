'use strict';
globalThis.AtlasLinkedMath = (() => {
  function project(point, matrix) {
    const h = matrix.map(row => row[0]*point[0]+row[1]*point[1]+row[2]*point[2]+row[3]);
    return h[2] > 1e-8 ? [h[0]/h[2], h[1]/h[2], h[2]] : null;
  }
  function barycentric(p, a, b, c) {
    const denominator=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
    if (Math.abs(denominator)<1e-10) return null;
    const u=((b[1]-c[1])*(p[0]-c[0])+(c[0]-b[0])*(p[1]-c[1]))/denominator;
    const v=((c[1]-a[1])*(p[0]-c[0])+(a[0]-c[0])*(p[1]-c[1]))/denominator;
    const w=1-u-v;
    return Math.min(u,v,w)>=-1e-8 ? [u,v,w] : null;
  }
  function interpolate(vertices, weights) {
    return [0,1,2].map(axis=>vertices.reduce((sum,p,i)=>sum+p[axis]*weights[i],0));
  }
  function pickImage(pixel, vertices, faces, matrix) {
    const projected=vertices.map(v=>project(v,matrix));
    let nearest=null;
    for (const face of faces) {
      const p=face.map(i=>projected[i]);
      if (p.some(v=>v===null)) continue;
      const b=barycentric(pixel,...p);
      if (!b) continue;
      const q=b.map((value,i)=>value/p[i][2]);
      const sum=q.reduce((a,b)=>a+b,0);
      const depth=1/sum;
      if (nearest && depth>=nearest.depth) continue;
      nearest={depth,point:interpolate(face.map(i=>vertices[i]),q.map(x=>x/sum))};
    }
    return nearest;
  }
  return {project,barycentric,interpolate,pickImage};
})();
