"""Catálogo curado de zonas de operación de Uruguay.

Fuentes de referencia: INE (localidades censales), Intendencia de Montevideo
(barrios) e Intendencia de Canelones (municipios). Las zonas son etiquetas
operativas, no límites geográficos ni una enumeración de todos los parajes.
https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/localidades-censales
https://montevideo.gub.uy/barrios
https://www.imcanelones.gub.uy/conozca/gobierno/municipios
"""

ALL_DEPARTMENT = "Todo el departamento"

URUGUAY_ZONES = {
    "ARTIGAS": ("Artigas", "Bella Unión", "Baltasar Brum", "Tomás Gomensoro"),
    "CANELONES": ("Canelones", "Ciudad de la Costa", "Las Piedras", "Pando", "La Paz", "Progreso", "Santa Lucía", "Sauce", "Toledo", "Barros Blancos", "Colonia Nicolich", "Paso Carrasco", "Salinas", "Atlántida", "Parque del Plata", "La Floresta", "San Jacinto", "San Ramón", "Tala", "Soca"),
    "CERRO LARGO": ("Melo", "Río Branco", "Fraile Muerto", "Isidoro Noblía", "Aceguá"),
    "COLONIA": ("Colonia del Sacramento", "Carmelo", "Nueva Helvecia", "Juan Lacaze", "Rosario", "Tarariras", "Nueva Palmira", "Ombúes de Lavalle"),
    "DURAZNO": ("Durazno", "Sarandí del Yí", "Carmen", "La Paloma", "Centenario"),
    "FLORES": ("Trinidad", "Ismael Cortinas", "Andresito"),
    "FLORIDA": ("Florida", "Sarandí Grande", "Casupá", "Fray Marcos", "25 de Mayo", "Cardal"),
    "LAVALLEJA": ("Minas", "José Pedro Varela", "Solís de Mataojo", "Mariscala", "Villa Serrana"),
    "MALDONADO": ("Maldonado", "Punta del Este", "San Carlos", "Piriápolis", "Pan de Azúcar", "Punta Ballena", "La Barra", "Manantiales", "José Ignacio", "Aiguá", "Solís Grande"),
    "MONTEVIDEO": ("Ciudad Vieja", "Centro", "Cordón", "Palermo", "Barrio Sur", "Parque Rodó", "Pocitos", "Punta Carretas", "Buceo", "Malvín", "Punta Gorda", "Carrasco", "Unión", "La Blanqueada", "Tres Cruces", "Parque Batlle", "Aguada", "Arroyo Seco", "Prado", "Atahualpa", "La Teja", "Belvedere", "Cerro", "Casabó", "Paso de la Arena", "Colón", "Lezica", "Peñarol", "Manga", "Piedras Blancas", "Maroñas", "Flor de Maroñas", "Casavalle", "Villa Española"),
    "PAYSANDÚ": ("Paysandú", "Guichón", "Quebracho", "Porvenir", "Piedras Coloradas"),
    "RÍO NEGRO": ("Fray Bentos", "Young", "Nuevo Berlín", "San Javier"),
    "RIVERA": ("Rivera", "Tranqueras", "Vichadero", "Minas de Corrales", "Mandubí"),
    "ROCHA": ("Rocha", "Chuy", "Castillos", "Lascano", "La Paloma", "La Pedrera", "Punta del Diablo", "Cabo Polonio", "Santa Teresa"),
    "SALTO": ("Salto", "Constitución", "Belén", "Colonia Lavalleja", "Termas del Daymán", "Termas del Arapey"),
    "SAN JOSÉ": ("San José de Mayo", "Ciudad del Plata", "Libertad", "Ecilda Paullier", "Rodríguez", "Rafael Perazza"),
    "SORIANO": ("Mercedes", "Dolores", "Cardona", "Palmitas", "José Enrique Rodó", "Villa Soriano"),
    "TACUAREMBÓ": ("Tacuarembó", "Paso de los Toros", "San Gregorio de Polanco", "Ansina", "Curtina"),
    "TREINTA Y TRES": ("Treinta y Tres", "Vergara", "Santa Clara de Olimar", "Cerro Chato", "General Enrique Martínez"),
}


def geography_payload():
    return {department: [ALL_DEPARTMENT, *zones] for department, zones in URUGUAY_ZONES.items()}
