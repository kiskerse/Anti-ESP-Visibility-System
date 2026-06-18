# Sugestões

Essa seção é apenas para sugerir funcionalidades atualizações do mecanismo, assim, no futuro, implementar-las. Também serve como anotações

## Trajetória Calculada

Um dos maiores problemas do FoW é justamente o efeito pop-in, que faz o jogador aparecer na tela de forma abrupta. Nesse contexto, há formas de resolver isso, um das técnicas que utilizei foi `Dead-Reckoning`, assim, posso realizar o fade-in e out com mais suavidade. Entretanto, combinar esse técnica às outras seria interessante. Uma delas é fazer uma trajetória mais curta (linha reta, mas, respeitando as paredes e os limites do mapa) e rápida para o cliente receber de forma suave.

### Isso não faria ser um movimento sem sentido ou com alguma velocidade absurda?

A resposta é: Depende, se o cliente não estiver vendo, de qualquer forma ele não verá a trajetória atrás da parede. Para o cheat, ele veria um boneco se locomovendo muito rápído no exato momento que o inimigo estiver aparecendo em sua tela, o que não seria uma grande vantagem.

> [!NOTE]
> Eu até demonstraria como seria, porém, ainda estou pensando em como fazer isso.

### Isso não seria pesado?

Provavelmente seria pouco escalável, porém, em um ambiente 5x5, a qual apenas 5 oponentes importam, provavelmente seria perfeitamente escalável. Com certeza o mais complicado será aplicar isso, já que você teria que adaptar isso apenas para longas distâncias, e, em pequenas, não utilizar esse mecanismo. Por exemplo

1. Em um ambiente onde o Ghost Player está longe do Player vivo, seria interessante utilizar essa técnica, já que a chance de haver um pop-in brusco é maior.
2. Em pequenas distâncias, com certeza seria utilizar uma bazuca para acabar com um formigueiro. Acredito que fade-in e fade-out suave seriam suficientes para esse caso.

Para entender melhor, pense que o Ghost player está em $ (1, 9) $ e o Player está, agora, em $ (10, 89) $. Ele subiu muito, então, seria interessante utilizar essa técnica, e calcular uma trajetória mais curta possível (não necessariamente essa rota ocorreu, mas para o cliente, não importa como ele chegou. Isso, em teoria, seria uma função de estado, o tempo que demorou não interessa para o cliente que não consegue ver a trajetória que ficará atrás da parede).

> [!CAUTION]
> Um possível problema seria uma trajetória curta que passasse pelo cliente (um caso que o inimigo estava atrás do cliente e desse a volta no mapa e ficar em sua frente. A trajetória mais rápida seria passar por ele).