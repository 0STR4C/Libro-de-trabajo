// Identidad visual; no cambia rutas, datos ni nombres de los contenedores.
document.title='Libro de Trabajo · Centro Operativo';
for(const selector of ['.brand','.login-heading']){
 const element=document.querySelector(selector);if(!element)continue;
 const mark=element.querySelector('span');if(mark){const image=document.createElement('img');image.src='/static/libro-trabajo.svg';image.alt='';image.width=46;image.height=46;mark.replaceWith(image)}
 if(selector==='.brand')element.querySelector('div').innerHTML='Libro de<br>Trabajo';
 else element.querySelector('h2').textContent='Ingresar a Libro de Trabajo';
}
const icon=document.createElement('link');icon.rel='icon';icon.href='/static/libro-trabajo.ico';document.head.appendChild(icon);
